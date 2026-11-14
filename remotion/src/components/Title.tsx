import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { safeInsets, TEXT_PADDING, TITLE_LINE_HEIGHT, titleLayout } from "../layout";
import type { TitleStyle } from "../types";

// 영상 상단 고정 제목. project.title(분석 단계에서 만든 20자 이내 제목)을 그대로 쓴다.

export const Title: React.FC<{
    text: string;
    style: TitleStyle;
    layout: ReturnType<typeof titleLayout>;
}> = ({ text, style, layout }) => {
    const frame = useCurrentFrame();
    const { fps } = useVideoConfig();
    const opacity = interpolate(frame / fps, [0, 0.3], [0, 1], { extrapolateRight: "clamp" });

    return (
        <div style={{
            position: "absolute",
            top: safeInsets.top + layout.top,
            left: safeInsets.left + TEXT_PADDING,
            right: safeInsets.right + TEXT_PADDING,
        }}>
            <div
                style={{
                    display: "-webkit-box",
                    WebkitBoxOrient: "vertical",
                    WebkitLineClamp: layout.lines,
                    overflow: "hidden",
                    overflowWrap: "anywhere",
                    textWrap: "balance",
                    color: style.color,
                    fontFamily: style.font,
                    fontSize: layout.size,
                    fontWeight: 900,
                    lineHeight: TITLE_LINE_HEIGHT,
                    letterSpacing: "-0.02em",
                    textAlign: "center",
                    wordBreak: "keep-all",
                    opacity,
                }}
            >
                {text}
            </div>
        </div>
    );
};
