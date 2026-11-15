import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { SAFE_HEIGHT, SAFE_WIDTH, safeInsets, subtitleLayout } from "../layout";
import type { SceneProps, SubtitleStyle } from "../types";
import { Subtitle } from "./Subtitle";

const numberGap = 20;
const defaultArtwork = { left: 0, top: 110, right: 1080, bottom: 1650 };

// 장면 하나 = 드로잉 영상(내레이션 포함) + 자막
export const SceneClip: React.FC<{
  scene: SceneProps;
  headerSpace: number;
  subtitleStyle: SubtitleStyle;
}> = ({ scene, headerSpace, subtitleStyle }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const time = frame / fps;
  const highlight = scene.numericHighlight;
  const bounds = scene.artworkBounds ?? defaultArtwork;
  const artworkWidth = bounds.right - bounds.left;
  const artworkHeight = bounds.bottom - bounds.top;
  const numberSize = highlight ? Math.min(88, SAFE_WIDTH / highlight.value.length) : 0;
  const numberHeight = highlight ? Math.ceil(numberSize * 1.1) + numberGap : 0;
  const subtitle = subtitleLayout(subtitleStyle.size, subtitleStyle.bottom);
  const artworkSpace = SAFE_HEIGHT - subtitle.space - numberHeight - headerSpace;
  const scale = Math.min(1, SAFE_WIDTH / artworkWidth, artworkSpace / artworkHeight);
  const artworkTop = headerSpace + (artworkSpace - artworkHeight * scale) / 2;
  const videoLeft = (SAFE_WIDTH - artworkWidth * scale) / 2 - bounds.left * scale;
  const videoTop = artworkTop - bounds.top * scale;

  return (
    <AbsoluteFill style={{ backgroundColor: "white" }}>
      <div style={{ position: "absolute", ...safeInsets, overflow: "hidden" }}>
        <OffthreadVideo
          src={staticFile(scene.video)}
          style={{
            position: "absolute",
            left: videoLeft,
            top: videoTop,
            width: width * scale,
            height: height * scale,
            // 영상 변환 과정에서 어두워진 흰색을 캔버스의 흰색에 맞춘다.
            filter: "brightness(1.025)",
          }}
        />
        {highlight && time >= highlight.start && (
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: artworkTop + artworkHeight * scale + numberGap,
              textAlign: "center",
              color: "#111",
              fontFamily: "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif",
              fontSize: numberSize,
              fontWeight: 900,
              lineHeight: 1.1,
            }}
          >
            {highlight.value}
          </div>
        )}
        <Subtitle cues={scene.cues} style={subtitleStyle} offset={subtitle.offset} />
      </div>
    </AbsoluteFill>
  );
};
