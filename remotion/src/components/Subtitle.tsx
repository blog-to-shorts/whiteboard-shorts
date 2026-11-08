import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue } from "../types";

// 화면 아래쪽 흰 여백(약 270px)에 자막을 표시한다.
// 자막이 바뀔 때 0.15초 동안 살짝 떠오르며 나타난다.
export const Subtitle: React.FC<{ cues: Cue[] }> = ({ cues }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const t = frame / fps;

    const cue = cues.find((c) => t >= c.start && t < c.end);
    if (!cue) return null;

    const since = t - cue.start;
    const opacity = interpolate(since, [0, 0.15], [0, 1], { extrapolateRight: "clamp" });
    const lift = interpolate(since, [0, 0.15], [12, 0], { extrapolateRight: "clamp" });

    return (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 110 }}>
            <div
                style={{
                    maxWidth: 960,
                    padding: "0 20px",
                    color: "#111",
                    fontFamily: "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif",
                    fontSize: 56,
                    fontWeight: 800,
                    lineHeight: 1.35,
                    textAlign: "center",
                    wordBreak: "keep-all",
                    opacity,
                    transform: `translateY(${lift}px)`,
                }}
            >
                {cue.text}
            </div>
        </AbsoluteFill>
    );
};