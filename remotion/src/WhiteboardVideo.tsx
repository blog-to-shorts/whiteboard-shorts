import React from "react";
import { AbsoluteFill, CalculateMetadataFunction, Series } from "remotion";
import { SceneClip } from "./components/SceneClip";
import { Title } from "./components/Title";
import { resolveStyle, type VideoProps } from "./types";

const secToFrames = (sec: number, fps: number) => Math.max(1, Math.round(sec * fps));

// 장면 수와 길이를 코드에 고정하지 않고 props(scenes.json)에서 계산한다.
export const calculateMetadata: CalculateMetadataFunction<VideoProps> = ({ props }) => {
    const fps = props.fps || 30;
    const durationInFrames = props.scenes.reduce((sum, s) => sum + secToFrames(s.duration, fps), 0);
    return { fps, durationInFrames: Math.max(durationInFrames, 1) };
};

export const WhiteboardVideo: React.FC<VideoProps> = ({ scenes, fps, title, style }) => {
    const st = resolveStyle(style);
    return (
        <AbsoluteFill style={{ backgroundColor: "white" }}>
            <Series>
                {scenes.map((scene) => (
                    <Series.Sequence key={scene.id} durationInFrames={secToFrames(scene.duration, fps || 30)}>
                        <SceneClip scene={scene} subtitleStyle={st.subtitle} />
                    </Series.Sequence>
                ))}
            </Series>
            {/* 제목은 장면이 바뀌어도 영상 내내 상단에 고정 */}
            {title ? <Title text={title} style={st.title} /> : null}
        </AbsoluteFill>
    );
};