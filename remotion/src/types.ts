// pipeline/src/pipeline/schema.py 와 필드를 맞춘다.
export type Scene = {
  id: number;
  narration: string;
  image_prompt: string;
  image?: string | null;
  audio?: string | null;
  video?: string | null;
  subtitle?: string | null;
  duration?: number | null;
  captions?: { start: number; end: number; text: string }[];
};

export const sceneFrames = (scene: Scene, fps: number): number =>
  Math.max(1, Math.ceil((scene.duration ?? 1) * fps));

export type ProjectProps = {
  title: string;
  aspect_ratio: string;
  fps: number;
  target_duration: number;
  style_prompt: string;
  scenes: Scene[];
  /** staticFile 기준 job 폴더 경로. 예: "jobs/20261105-xxxx" */
  assetBase?: string;
};
