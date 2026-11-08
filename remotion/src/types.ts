// scenes.json → s08_render.py가 Remotion에 넘기는 props 형식.
// pipeline/src/pipeline/schema.py와 필드 이름을 맞춘다.

export type Cue = {
  start: number; // 장면 시작 기준 초
  end: number;
  text: string;
};

export type SceneProps = {
  id: number;
  narration: string;
  video: string; // public 폴더(= job 폴더) 기준 경로, 예: videos/scene_01.1080.mp4
  duration: number; // 초 (실제 음성 길이)
  cues: Cue[];
};

export type VideoProps = {
  title: string;
  fps: number;
  scenes: SceneProps[];
};