import { useEffect, useMemo, useState } from "react";
import { api, FontInfo, Job, JobStyle } from "./api";

// 자막·제목 모양 고르기. 오른쪽 미리보기는 실제 영상(1080×1920) 배치를 줄여 그린 것이고,
// "다시 만들기"를 누르면 자막·영상 합성만 다시 해서(API 비용 없음) 영상에 반영한다.
// 배치 숫자는 pipeline config.py 기본값과 같다 (IMAGE_TOP 360 / IMAGE_HEIGHT 1000 / SUBTITLE_BOTTOM 400 / TITLE_TOP 150)
const W = 1080, H = 1920, IMG_TOP = 360, IMG_H = 1000, IMG_W = Math.round((IMG_H * 854) / 1280), SUB_BOTTOM = 400, TITLE_TOP = 150;
const SCALE = 0.25;
const DEFAULT_CSS = "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif";
const DEFAULT: JobStyle = { subtitle_font: "", subtitle_size: 56, title_show: true, title_font: "", title_size: 80 };

// 미리보기에서도 같은 구글 폰트를 쓰도록 필요할 때 불러온다
function loadGoogleFont(font?: FontInfo) {
  if (!font?.google) return;
  const id = `gf-${font.key}`;
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = `https://fonts.googleapis.com/css2?family=${font.google.replace(/ /g, "+")}&display=swap`;
  document.head.appendChild(link);
}

// pipeline s07과 같은 기준: 1080px 폭에서 글씨 56일 때 한 줄 19자
const lineChars = (size: number) => Math.max(8, Math.round((19 * 56) / size));

// 첫 장면 자막 앞부분을 실제 영상처럼 최대 두 줄로 나눠 보여 준다
function wrapSample(text: string, chars: number) {
  const lines: string[] = [];
  let cur = "";
  for (const w of text.split(/\s+/)) {
    if (cur && (cur + " " + w).length > chars) {
      lines.push(cur);
      cur = w;
      if (lines.length === 2) break;
    } else cur = cur ? `${cur} ${w}` : w;
  }
  if (lines.length < 2 && cur) lines.push(cur);
  return lines.slice(0, 2).join("\n");
}

export function StylePanel({ job, onApplied }: { job: Job; onApplied: () => void }) {
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const [draft, setDraft] = useState<JobStyle>(job.style ?? DEFAULT);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.fonts().then(setFonts).catch(() => setFonts([]));
  }, []);
  // 다른 작업을 고르거나 다시 만든 뒤에는 서버 값으로 맞춘다
  const savedKey = JSON.stringify(job.style ?? DEFAULT);
  useEffect(() => {
    setDraft(job.style ?? DEFAULT);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.job_id, savedKey]);

  const byKey = useMemo(() => Object.fromEntries(fonts.map((f) => [f.key, f])), [fonts]);
  const subFont: FontInfo | undefined = byKey[draft.subtitle_font];
  const titleFont: FontInfo | undefined = byKey[draft.title_font] ?? subFont;
  useEffect(() => {
    loadGoogleFont(subFont);
    loadGoogleFont(titleFont);
  }, [subFont, titleFont]);

  if (job.scenes.length === 0) return null;
  const locked = job.status === "queued" || job.status === "running";
  const changed = JSON.stringify(draft) !== savedKey;
  const set = <K extends keyof JobStyle>(k: K, v: JobStyle[K]) => setDraft((d) => ({ ...d, [k]: v }));

  const firstSub = job.scenes[0].subtitle_text ?? job.scenes[0].narration;
  const sample = wrapSample(firstSub, lineChars(draft.subtitle_size));
  const subCss = subFont?.css ?? DEFAULT_CSS;
  const titleCss = titleFont?.css ?? subCss;
  // 긴 제목은 Remotion Title과 같은 방식으로 줄어든다
  const title = job.title ?? "제목";
  const units = [...title].reduce((w, ch) => w + (ch === " " ? 0.35 : /[\x00-\x7F]/.test(ch) ? 0.6 : 1), 0);
  const titleSize = Math.round(Math.max(draft.title_size * 0.7, Math.min(draft.title_size, 960 / Math.max(units, 1))));

  const apply = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.setStyle(job.job_id, draft);
      onApplied();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
      <div className="style-panel">
        <h3><span className="sq" />Subtitle Style<sup>{"{Aa}"}</sup></h3>
        <div className="style-grid">
          <div className="style-controls">
            <label>
              <span>자막 글꼴</span>
              <select value={draft.subtitle_font} onChange={(e) => set("subtitle_font", e.target.value)}>
                {fonts.map((f) => <option key={f.key} value={f.key === "malgun" ? "" : f.key}>{f.label}</option>)}
              </select>
            </label>
            <label>
              <span>자막 크기 <b>{draft.subtitle_size}px</b> · 한 줄 약 {lineChars(draft.subtitle_size)}자</span>
              <input type="range" min={36} max={96} step={2} value={draft.subtitle_size}
                     onChange={(e) => set("subtitle_size", Number(e.target.value))} />
            </label>
            <label className="check">
              <input type="checkbox" checked={draft.title_show} onChange={(e) => set("title_show", e.target.checked)} />
              <span>상단 제목 표시 (AI가 만든 제목: {job.title ?? "-"})</span>
            </label>
            {draft.title_show && (
                <>
                  <label>
                    <span>제목 글꼴</span>
                    <select value={draft.title_font} onChange={(e) => set("title_font", e.target.value)}>
                      <option value="">자막과 같게</option>
                      {fonts.filter((f) => f.key !== "malgun").map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                  </label>
                  <label>
                    <span>제목 크기 <b>{draft.title_size}px</b></span>
                    <input type="range" min={48} max={140} step={2} value={draft.title_size}
                           onChange={(e) => set("title_size", Number(e.target.value))} />
                  </label>
                </>
            )}
            {err && <p className="error-box">{err}</p>}
            <div className="scene-edit-foot">
              <span className="hint">
                {locked ? "영상을 만드는 중이에요" : changed ? "자막·합성만 다시 만들어요 (API 비용 없음)" : "지금 영상과 같아요"}
              </span>
              <button className="ghost" disabled={!changed || busy} onClick={() => setDraft(job.style ?? DEFAULT)}>되돌리기</button>
              <button className="cta" disabled={!changed || busy || locked} onClick={apply}>
                {busy ? "요청 중…" : "이 스타일로 다시 만들기 →"}
              </button>
            </div>
          </div>

          <div className="style-preview" style={{ width: W * SCALE, height: H * SCALE }} aria-label="자막 미리보기">
            {draft.title_show && (
                <div className="sp-title" style={{ top: TITLE_TOP * SCALE, fontFamily: titleCss, fontSize: titleSize * SCALE }}>{title}</div>
            )}
            <div className="sp-image" style={{ top: IMG_TOP * SCALE, height: IMG_H * SCALE, width: IMG_W * SCALE }}>그림</div>
            <div className="sp-sub" style={{ bottom: SUB_BOTTOM * SCALE, fontFamily: subCss, fontSize: draft.subtitle_size * SCALE }}>{sample}</div>
            <div className="sp-ui" style={{ height: SUB_BOTTOM * SCALE * 0.8 }}>쇼츠 재생바·버튼 영역</div>
          </div>
        </div>
      </div>
  );
}
