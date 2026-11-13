import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

// 웹에서 고를 수 있는 구글 폰트 (pipeline/style.py의 FONTS와 이름을 맞춘다). 값 = 불러올 굵기
const GOOGLE_FONTS: Record<string, string> = {
    "Noto Sans KR": "wght@400;700;900",
    "Nanum Gothic": "wght@400;700;800",
    "Gothic A1": "wght@400;700;800;900",
    "Nanum Myeongjo": "wght@400;700;800",
    "Black Han Sans": "",
    "Do Hyeon": "",
    "Jua": "",
    "Gowun Dodum": "",
    "Nanum Pen Script": "",
};

const firstFamily = (css: string) => css.split(",")[0].trim().replace(/^['"]|['"]$/g, "");

// font-family 첫 글꼴이 구글 폰트면 내려받을 때까지 렌더를 잠시 멈춘다 (PC에 없는 글꼴도 영상에 똑같이 나오게)
export const useGoogleFont = (css: string) => {
    const name = firstFamily(css);
    const [handle] = useState(() => (name in GOOGLE_FONTS ? delayRender(`font ${name}`) : null));
    useEffect(() => {
        if (handle === null) return;
        const id = `gf-${name.replace(/\s+/g, "-")}`;
        if (!document.getElementById(id)) {
            const link = document.createElement("link");
            link.id = id;
            link.rel = "stylesheet";
            const axis = GOOGLE_FONTS[name] ? `:${GOOGLE_FONTS[name]}` : "";
            link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(name).replace(/%20/g, "+")}${axis}&display=block`;
            document.head.appendChild(link);
        }
        const done = () => continueRender(handle);
        const timeout = setTimeout(done, 15000); // 네트워크가 안 되면 기본 글꼴로라도 진행
        (async () => {
            for (let i = 0; i < 50 && ![...document.styleSheets].some((s) => s.href?.includes(encodeURIComponent(name).replace(/%20/g, "+"))); i++) {
                await new Promise((r) => setTimeout(r, 100));
            }
            await Promise.all([document.fonts.load(`400 40px "${name}"`), document.fonts.load(`800 40px "${name}"`)]).catch(() => {});
            clearTimeout(timeout);
            done();
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [handle]);
};
