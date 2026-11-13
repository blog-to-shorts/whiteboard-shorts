import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";
import type { SceneProps, SubtitleStyle } from "../types";
import { Subtitle } from "./Subtitle";

// 장면 하나 = 드로잉 영상(내레이션 포함) + 자막
export const SceneClip: React.FC<{ scene: SceneProps; subtitleStyle: SubtitleStyle }> = ({ scene, subtitleStyle }) => {
  return (
      <AbsoluteFill style={{ backgroundColor: "white" }}>
        <OffthreadVideo src={staticFile(scene.video)} />
        <Subtitle cues={scene.cues} style={subtitleStyle} />
      </AbsoluteFill>
  );
};