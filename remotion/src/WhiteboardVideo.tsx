import { AbsoluteFill, Series, useVideoConfig } from "remotion";
import { SceneClip } from "./components/SceneClip";
import type { ProjectProps } from "./types";

export const WhiteboardVideo: React.FC<ProjectProps> = ({ scenes, assetBase = "" }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "white" }}>
      <Series>
        {scenes.map((scene) => (
          <Series.Sequence key={scene.id} durationInFrames={Math.ceil((scene.duration ?? 1) * fps)}>
            <SceneClip scene={scene} assetBase={assetBase} />
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
};
