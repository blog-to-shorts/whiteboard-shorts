import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { TitleStyle } from "../types";

// 영상 상단 고정 제목. project.title(분석 단계에서 만든 20자 이내 제목)을 그대로 쓴다.
// 한 줄에 다 안 들어가면 글씨를 줄이고(최소 70%), 그래도 길면 두 줄로 넘긴다.
const MAX_WIDTH = 960;

export const Title: React.FC<{ text: string; style: TitleStyle }> = ({ text, style }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const opacity = interpolate(frame / fps, [0, 0.3], [0, 1], { extrapolateRight: "clamp" });

    // 한글 한 글자 폭 ≈ 글씨 크기, 띄어쓰기 ≈ 0.35배로 어림해서 한 줄에 맞춘다
    const units = [...text].reduce((w, ch) => w + (ch === " " ? 0.35 : /[\x00-\x7F]/.test(ch) ? 0.6 : 1), 0);
    const fit = units > 0 ? MAX_WIDTH / units : style.size;
    const size = Math.round(Math.max(style.size * 0.7, Math.min(style.size, fit)));

    return (
        <AbsoluteFill style={{ alignItems: "center", paddingTop: style.top }}>
            <div
                style={{
                    maxWidth: MAX_WIDTH,
                    color: style.color,
                    fontFamily: style.font,
                    fontSize: size,
                    fontWeight: 900,
                    lineHeight: 1.2,
                    letterSpacing: "-0.02em",
                    textAlign: "center",
                    wordBreak: "keep-all",
                    opacity,
                }}
            >
                {text}
            </div>
        </AbsoluteFill>
    );
};
