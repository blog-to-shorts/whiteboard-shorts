import { Composition } from "remotion";
import { WhiteboardVideo } from "./WhiteboardVideo";
import type { ProjectProps } from "./types";

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
      const total = props.scenes.reduce((s, sc) => s + (sc.duration ?? 0), 0);
      return { durationInFrames: Math.max(1, Math.ceil(total * FPS)) };
    }}
  />
);
