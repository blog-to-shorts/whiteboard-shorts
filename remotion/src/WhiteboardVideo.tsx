import React from "react";
import { AbsoluteFill, CalculateMetadataFunction, Img, Series } from "remotion";
import { SceneClip, safeInsets } from "./components/SceneClip";
import type { VideoProps } from "./types";

const secToFrames = (sec: number, fps: number) => Math.max(1, Math.round(sec * fps));

// 장면 수와 길이를 코드에 고정하지 않고 props(scenes.json)에서 계산한다.
export const calculateMetadata: CalculateMetadataFunction<VideoProps> = ({ props }) => {
    const fps = props.fps || 30;
    const durationInFrames = props.scenes.reduce((sum, s) => sum + secToFrames(s.duration, fps), 0);
    return { fps, durationInFrames: Math.max(durationInFrames, 1) };
};

export const WhiteboardVideo: React.FC<VideoProps> = ({ scenes, fps, introLogo }) => {
    return (
        <AbsoluteFill style={{ backgroundColor: "white" }}>
            <Series>
                {scenes.map((scene) => (
                    <Series.Sequence key={scene.id} durationInFrames={secToFrames(scene.duration, fps || 30)}>
                        <SceneClip scene={scene} hasBrandLogo={Boolean(introLogo)} />
                    </Series.Sequence>
                ))}
            </Series>
            {introLogo && (
                <Img
                    src={introLogo}
                    alt="스마트동스쿨"
                    style={{ position: "absolute", top: safeInsets.top, left: safeInsets.left + 8, width: 200 }}
                />
            )}
        </AbsoluteFill>
    );
};
