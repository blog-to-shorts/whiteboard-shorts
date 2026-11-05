import { AbsoluteFill, Audio, OffthreadVideo, staticFile } from "remotion";
import { Subtitle } from "./Subtitle";
import type { Scene } from "../types";

const asset = (base: string, p?: string | null) => (p ? staticFile(`${base}/${p}`) : undefined);

export const SceneClip: React.FC<{ scene: Scene; assetBase: string }> = ({ scene, assetBase }) => {
  const video = asset(assetBase, scene.video);
  const audio = asset(assetBase, scene.audio);
  return (
    <AbsoluteFill>
      {video && <OffthreadVideo src={video} muted style={{ width: "100%", height: "100%", objectFit: "contain" }} />}
      {audio && <Audio src={audio} />}
      <Subtitle text={scene.narration} />
    </AbsoluteFill>
  );
};
