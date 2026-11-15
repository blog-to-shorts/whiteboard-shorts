// FastAPI 호출. vite.config.ts의 프록시로 /api → http://localhost:8000

export type JobStatus = "queued" | "running" | "done" | "error";

export type Scene = {
  id: number;
  narration: string;
  subtitle_text: string | null;
  image_prompt: string | null;
  duration: number | null;
};

export type SceneEdit = { id: number; narration?: string; subtitle_text?: string; image_prompt?: string };

export type JobStyle = {
  subtitle_font: string; // FontInfo.key, 빈 값 = 기본 글꼴
  subtitle_size: number;
  subtitle_color: string; // #rrggbb
  subtitle_bottom: number; // 화면 아래에서 자막 아랫변까지(px, 1920 기준)
  title_show: boolean;
  title_font: string;
  title_size: number;
  title_color: string;
};

export type FontInfo = { key: string; label: string; group: string; css: string; google: string | null; url: string | null };

export type Job = {
  job_id: string;
  status: JobStatus;
  source_url: string | null;
  title: string | null;
  current_step: string | null;
  steps: { step: string; status: string; seconds: number | null }[];
  scenes: Scene[];
  duration: number | null;
  total_seconds: number | null;
  video_url: string | null;
  error: string | null;
  queue_position: number | null;
  style: JobStyle | null;
};

const BASE = "/api";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `요청 실패 (${res.status})`);
  }
  return res.json();
}

export const api = {
  create: (urls: string[]) =>
    call<{ job_ids: string[] }>("/jobs", { method: "POST", body: JSON.stringify({ urls }) }),
  createFromText: (text: string) =>
    call<{ job_ids: string[] }>("/jobs", { method: "POST", body: JSON.stringify({ text }) }),
  list: () => call<Job[]>("/jobs"),
  get: (id: string) => call<Job>(`/jobs/${id}`),
  rerun: (id: string, edits: SceneEdit[]) =>
      call<Job>(`/jobs/${id}/rerun`, { method: "POST", body: JSON.stringify({ edits }) }),
  fonts: () => call<FontInfo[]>("/jobs/fonts"),
  setStyle: (id: string, style: JobStyle) =>
      call<Job>(`/jobs/${id}/style`, { method: "PUT", body: JSON.stringify(style) }),
  videoUrl: (job: Job) => (job.video_url ? BASE + job.video_url : null),
  downloadUrl: (job: Job) => (job.video_url ? `${BASE}${job.video_url}&download=true` : null),
};

// 파이프라인 단계 이름 → 화면 표시용
export const STEP_LABELS: Record<string, string> = {
  s01_extract: "본문 추출",
  s02_analyze: "핵심 분석",
  s03_script: "대본 작성",
  s05_tts: "음성 생성",
  s04_image: "그림 생성",
  s06_animate: "드로잉",
  s07_subtitle: "자막",
  s08_render: "영상 합성",
};
export const STEP_ORDER = Object.keys(STEP_LABELS);
