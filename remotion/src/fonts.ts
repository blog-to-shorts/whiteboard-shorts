import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

const firstFamily = (css: string) => css.split(",")[0].trim().replace(/^['"]|['"]$/g, "");

// 눈누 폰트: 파일 주소로 바로 등록한다. 굵기 파일이 하나뿐이라 100~900 전체에 같은 파일을 쓴다(가짜 굵게 방지)
// 자막·제목이 같은 글꼴이면 한 번만 내려받고, 두 쪽 모두 다 받을 때까지 기다린다
const fileLoads = new Map<string, Promise<void>>();
const loadFontFile = (name: string, url: string) => {
    if (!fileLoads.has(name)) {
        const face = new FontFace(name, `url("${encodeURI(url)}")`, { weight: "100 900" });
        fileLoads.set(name, face.load().then((f) => void document.fonts.add(f)));
    }
    return fileLoads.get(name)!;
};

// 웹 글꼴을 내려받을 때까지 렌더를 잠시 멈춘다 (PC에 없는 글꼴도 영상에 똑같이 나오게).
// spec: pipeline/style.py FONTS의 google 값 (예: "Noto+Sans+KR:wght@400;700;900")
// url: 눈누 폰트 파일 주소. 둘 다 비어 있으면 PC 글꼴을 쓴다.
export const useWebFont = (css: string, spec?: string, url?: string) => {
    const name = firstFamily(css);
    const [handle] = useState(() => (spec || url ? delayRender(`font ${name}`) : null));
    useEffect(() => {
        if (handle === null) return;
        if (url) {
            let finished = false;
            const done = () => {
                if (!finished) {
                    finished = true;
                    continueRender(handle);
                }
            };
            const timeout = setTimeout(done, 15000);
            loadFontFile(name, url)
                .catch(() => undefined) // 실패하면 기본 글꼴로 진행
                .finally(() => {
                    clearTimeout(timeout);
                    done();
                });
            return;
        }
        if (!spec) return;
        const href = `https://fonts.googleapis.com/css2?family=${spec}&display=block`;
        let link = document.querySelector<HTMLLinkElement>(`link[data-gf="${spec}"]`);
        if (!link) {
            link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = href;
            link.dataset.gf = spec;
            document.head.appendChild(link);
        }
        let finished = false;
        const done = () => {
            if (!finished) {
                finished = true;
                continueRender(handle);
            }
        };
        const timeout = setTimeout(done, 15000); // 네트워크가 안 되면 기본 글꼴로라도 진행
        const waitCss = new Promise<void>((resolve) => {
            if (link!.sheet) return resolve();
            link!.addEventListener("load", () => resolve(), { once: true });
            link!.addEventListener("error", () => resolve(), { once: true });
        });
        waitCss
            .then(() => Promise.all([document.fonts.load(`400 40px "${name}"`), document.fonts.load(`800 40px "${name}"`)]))
            .catch(() => undefined)
            .finally(() => {
                clearTimeout(timeout);
                done();
            });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [handle]);
};
