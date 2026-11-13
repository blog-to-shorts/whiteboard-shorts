import React from "react";
import { Composition } from "remotion";
import { WhiteboardVideo, calculateMetadata } from "./WhiteboardVideo";
import { videoSchema } from "./schema";

// Studio 미리보기용 기본값. 실제 렌더 때는 s08_render.py가 job의 props로 덮어쓴다.
// Studio에서 --props로 job의 title/scenes만 넘기면, 아래 style은 오른쪽 Props 패널에서 바로 바꿔 볼 수 있다.
export const RemotionRoot: React.FC = () => {
    return (
        <Composition
            id="WhiteboardVideo"
            component={WhiteboardVideo}
            schema={videoSchema}
            width={1080}
            height={1920}
            fps={30}
            durationInFrames={30}
            defaultProps={{
                title: "미리보기",
                fps: 30,
                scenes: [],
                style: {
                    subtitle: {
                        font: "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif",
                        size: 56,
                        weight: 800,
                        color: "#111111",
                        bottom: 400,
                    },
                    title: {
                        font: "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif",
                        size: 80,
                        color: "#111111",
                        top: 150,
                    },
                },
            }}
            calculateMetadata={calculateMetadata}
        />
    );
};
