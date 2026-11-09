import { AbsoluteFill, Audio, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Subtitle } from "./Subtitle";
import type { Scene } from "../types";

const asset = (base: string, p?: string | null) =>
  p ? staticFile(base ? `${base}/${p}` : p) : undefined;

export const SceneClip: React.FC<{ scene: Scene; assetBase: string }> = ({ scene, assetBase }) => {
  const video = asset(assetBase, scene.video);
  const audio = asset(assetBase, scene.audio);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = frame / fps;
  const caption = scene.captions?.find(({ start, end }) => start <= time && time < end);
  const text = scene.captions ? caption?.text : scene.narration;
  return (
    <AbsoluteFill>
      {video && <OffthreadVideo src={video} muted style={{ width: "100%", height: "100%", objectFit: "contain" }} />}
      {audio && <Audio src={audio} />}
      {text && <Subtitle text={text} />}
    </AbsoluteFill>
  );
};
