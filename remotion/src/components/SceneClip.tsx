import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { SceneProps } from "../types";
import { Subtitle } from "./Subtitle";

// 1080×1920 기준. 오른쪽은 반응 버튼, 하단은 게시물 정보와 탐색 UI를 위해 더 비운다.
export const safeInsets = { top: 280, right: 252, bottom: 680, left: 108 };
// 기존 56px 자막이 좁은 안전 영역에서 네 줄로 표시될 수 있다.
const subtitleSpace = 336;
const numberGap = 20;
const brandLogoSpace = 104;
const defaultArtwork = { left: 0, top: 110, right: 1080, bottom: 1650 };

// 장면 하나 = 드로잉 영상(내레이션 포함) + 자막
export const SceneClip: React.FC<{ scene: SceneProps; hasBrandLogo: boolean }> = ({ scene, hasBrandLogo }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const time = frame / fps;
  const highlight = scene.numericHighlight;
  const bounds = scene.artworkBounds ?? defaultArtwork;
  const safeWidth = width - safeInsets.left - safeInsets.right;
  const safeHeight = height - safeInsets.top - safeInsets.bottom;
  const artworkWidth = bounds.right - bounds.left;
  const artworkHeight = bounds.bottom - bounds.top;
  const numberSize = highlight ? Math.min(88, safeWidth / highlight.value.length) : 0;
  const numberHeight = highlight ? Math.ceil(numberSize * 1.1) + numberGap : 0;
  const logoSpace = hasBrandLogo ? brandLogoSpace : 0;
  const artworkSpace = safeHeight - subtitleSpace - numberHeight - logoSpace;
  const scale = Math.min(1, safeWidth / artworkWidth, artworkSpace / artworkHeight);
  const artworkTop = logoSpace + (artworkSpace - artworkHeight * scale) / 2;
  const videoLeft = (safeWidth - artworkWidth * scale) / 2 - bounds.left * scale;
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
        <Subtitle cues={scene.cues} safeArea />
      </div>
    </AbsoluteFill>
  );
};
