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

// 자막·제목 모양. .env(SUBTITLE_*, TITLE_*) → config.py → s08_render.py로 들어온다.
// 빠진 값은 DEFAULT_STYLE로 채운다.
export type SubtitleStyle = {
  font: string;
  size: number; // px
  weight: number;
  color: string;
  bottom: number; // 화면 아래에서 자막 아랫변까지(px). 쇼츠 재생바 위로 올리는 값
  google?: string; // 구글 폰트 CSS2 family 값. 비어 있으면 PC 글꼴
  url?: string; // 눈누 폰트 파일 주소
};

export type TitleStyle = {
  font: string;
  size: number; // px. 긴 제목은 자동으로 줄어든다
  color: string;
  top: number; // 화면 위에서 제목 윗변까지(px)
  google?: string;
  url?: string;
};

export type VideoStyle = {
  subtitle: SubtitleStyle;
  title: TitleStyle;
};

const FONT = "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif";

export const DEFAULT_STYLE: VideoStyle = {
  subtitle: { font: FONT, size: 56, weight: 800, color: "#111111", bottom: 400 },
  title: { font: FONT, size: 80, color: "#111111", top: 150 },
};

export const resolveStyle = (style?: Partial<{ subtitle: Partial<SubtitleStyle>; title: Partial<TitleStyle> }>): VideoStyle => ({
  subtitle: { ...DEFAULT_STYLE.subtitle, ...(style?.subtitle ?? {}) },
  title: { ...DEFAULT_STYLE.title, ...(style?.title ?? {}) },
});

export type VideoProps = {
  title: string; // 비어 있으면 상단 제목을 그리지 않는다
  fps: number;
  scenes: SceneProps[];
  style?: Partial<{ subtitle: Partial<SubtitleStyle>; title: Partial<TitleStyle> }>;
};