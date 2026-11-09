import { Composition } from "remotion";
import { WhiteboardVideo } from "./WhiteboardVideo";
import { sceneFrames, type ProjectProps } from "./types";

const FPS = 30;

const defaultProps: ProjectProps = {
  title: "preview",
  aspect_ratio: "9:16",
  fps: FPS,
  target_duration: 45,
  style_prompt: "",
  scenes: [],
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="WhiteboardVideo"
    component={WhiteboardVideo}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={FPS * 5}
    defaultProps={defaultProps}
    // 장면 수·길이를 JSON에서 읽어 총 길이를 계산
    calculateMetadata={({ props }) => {
      const fps = props.fps;
      const total = props.scenes.reduce((sum, scene) => sum + sceneFrames(scene, fps), 0);
      return { fps, durationInFrames: Math.max(1, total) };
    }}
  />
);
