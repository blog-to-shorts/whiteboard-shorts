import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

const firstFamily = (css: string) => css.split(",")[0].trim().replace(/^['"]|['"]$/g, "");

// 구글 폰트를 내려받을 때까지 렌더를 잠시 멈춘다 (PC에 없는 글꼴도 영상에 똑같이 나오게).
// spec은 pipeline/style.py FONTS의 google 값 그대로 (예: "Noto+Sans+KR:wght@400;700;900"). 비어 있으면 PC 글꼴을 쓴다.
export const useGoogleFont = (css: string, spec?: string) => {
    const name = firstFamily(css);
    const [handle] = useState(() => (spec ? delayRender(`font ${name}`) : null));
    useEffect(() => {
        if (handle === null || !spec) return;
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
