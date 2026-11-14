import React from "react";
import { Composition } from "remotion";
import { WhiteboardVideo, calculateMetadata } from "./WhiteboardVideo";
import { VIDEO_HEIGHT, VIDEO_WIDTH } from "./layout";
import { DEFAULT_STYLE } from "./types";
import { videoSchema } from "./schema";

// Studio 미리보기용 기본값. 실제 렌더 때는 s08_render.py가 job의 props로 덮어쓴다.
// Studio에서 --props로 job의 title/scenes만 넘기면, 아래 style은 오른쪽 Props 패널에서 바로 바꿔 볼 수 있다.
export const RemotionRoot: React.FC = () => {
    return (
        <Composition
            id="WhiteboardVideo"
            component={WhiteboardVideo}
            schema={videoSchema}
            width={VIDEO_WIDTH}
            height={VIDEO_HEIGHT}
            fps={30}
            durationInFrames={30}
            defaultProps={{
                title: "미리보기",
                fps: 30,
                scenes: [],
                style: DEFAULT_STYLE,
            }}
            calculateMetadata={calculateMetadata}
        />
    );
};
