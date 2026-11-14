import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SUBTITLE_LINE_HEIGHT, TEXT_PADDING } from "../layout";
import type { Cue, SubtitleStyle } from "../types";

// 그림 아래, 안전 영역 안에 자막을 표시한다.
// 자막이 바뀔 때 0.15초 동안 살짝 떠오르며 나타난다.
export const Subtitle: React.FC<{ cues: Cue[]; style: SubtitleStyle; offset: number }> = ({ cues, style, offset }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const t = frame / fps;

    const cue = cues.find((c) => t >= c.start && t < c.end);
    if (!cue) return null;

    const since = t - cue.start;
    const opacity = interpolate(since, [0, 0.15], [0, 1], { extrapolateRight: "clamp" });
    const lift = interpolate(since, [0, 0.15], [12, 0], { extrapolateRight: "clamp" });

    return (
        <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: offset }}>
            <div
                style={{
                    width: "100%",
                    padding: `0 ${TEXT_PADDING}px`,
                    boxSizing: "border-box",
                    overflowWrap: "anywhere",
                    color: style.color,
                    fontFamily: style.font,
                    fontSize: style.size,
                    fontWeight: style.weight,
                    lineHeight: SUBTITLE_LINE_HEIGHT,
                    textAlign: "center",
                    wordBreak: "keep-all",
                    whiteSpace: "pre-line", // 자막에 넣은 줄바꿈(\n)을 그대로 표시
                    opacity,
                    transform: `translateY(${lift}px)`,
                }}
            >
                {cue.text}
            </div>
        </AbsoluteFill>
    );
};
