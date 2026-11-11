import React from "react";
import { Composition } from "remotion";
import { WhiteboardVideo, calculateMetadata } from "./WhiteboardVideo";
import type { VideoProps } from "./types";

// Studio 미리보기용 기본값. 실제 렌더 때는 s08_render.py가 job의 props로 덮어쓴다.
const defaultProps: VideoProps = {
    title: "미리보기",
    fps: 30,
    scenes: [],
};

export const RemotionRoot: React.FC = () => {
    return (
        <Composition
            id="WhiteboardVideo"
            component={WhiteboardVideo}
            width={1080}
            height={1920}
            fps={30}
            durationInFrames={30}
            defaultProps={defaultProps}
            calculateMetadata={calculateMetadata}
        />
    );
};