import { useEffect, useMemo, useRef, useState } from "react";
import { api, FontInfo, Job, JobStyle } from "./api";
import { ColorPalette } from "./ColorPalette";
import logo from "../../remotion/public/brand/smartdongschool-logo.png?url";
import {
  DEFAULT_SUBTITLE_BOTTOM, LOGO_LEFT, LOGO_WIDTH, MAX_SUBTITLE_BOTTOM, SAFE_HEIGHT,
  safeInsets, subtitleLayout, subtitleLineChars as lineChars, TEXT_PADDING,
  TITLE_LINE_HEIGHT, titleLayout, VIDEO_HEIGHT as H, VIDEO_WIDTH as W,
} from "../../remotion/src/layout";

// 자막·제목 모양 고르기. 오른쪽 미리보기는 실제 영상(1080×1920) 배치를 줄여 그린 것이고,
// "다시 만들기"를 누르면 자막·영상 합성만 다시 해서(API 비용 없음) 영상에 반영한다.
const BOTTOM_MIN = DEFAULT_SUBTITLE_BOTTOM;
const BOTTOM_MAX = MAX_SUBTITLE_BOTTOM;
const BOTTOM_DEFAULT = DEFAULT_SUBTITLE_BOTTOM;
const SCALE = 0.25;
const DEFAULT_CSS = "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif";
const DEFAULT: JobStyle = {
  subtitle_font: "", subtitle_size: 56, subtitle_color: "#111111", subtitle_bottom: BOTTOM_DEFAULT,
  title_show: true, title_font: "", title_size: 80, title_color: "#111111",
};

// 미리보기에서도 같은 글꼴을 쓰도록 필요할 때 불러온다 (눈누 폰트는 파일 주소, 구글 폰트는 CSS)
const loaded = new Set<string>();
function loadGoogleFont(font?: FontInfo) {
  if (font?.url && !loaded.has(font.key)) {
    loaded.add(font.key);
    const name = font.css.split(",")[0].trim().replace(/^'|'$/g, "");
    new FontFace(name, `url("${encodeURI(font.url)}")`, { weight: "100 900" }).load()
        .then((f) => document.fonts.add(f))
        .catch(() => loaded.delete(font.key));
    return;
  }
  if (!font?.google) return;
  const id = `gf-${font.key}`;
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = `https://fonts.googleapis.com/css2?family=${font.google}&display=swap`;
  document.head.appendChild(link);
}

// 첫 장면 자막 앞부분으로 글꼴과 줄바꿈을 확인한다.
function wrapSample(text: string, chars: number) {
  const sample = text.trim();
  if (sample.length <= chars) return sample;
  const breakAt = sample.lastIndexOf(" ", chars);
  const cut = breakAt > 0 ? breakAt : chars;
  return sample.slice(0, cut) + "\n" + sample.slice(cut).trimStart().slice(0, chars).trimEnd();
}

// 글꼴 목록을 고딕·명조·제목용·손글씨로 묶어 보여 준다
function FontOptions({ fonts, skipDefault }: { fonts: FontInfo[]; skipDefault?: boolean }) {
  const groups: Record<string, FontInfo[]> = {};
  for (const f of fonts) {
    if (skipDefault && f.key === "malgun") continue;
    (groups[f.group] ??= []).push(f);
  }
  return (
      <>
        {Object.entries(groups).map(([g, list]) => (
            <optgroup key={g} label={g}>
              {list.map((f) => <option key={f.key} value={f.key === "malgun" ? "" : f.key}>{f.label}</option>)}
            </optgroup>
        ))}
      </>
  );
}

export function StylePanel({ job, onApplied }: { job: Job; onApplied: () => void }) {
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const [draft, setDraft] = useState<JobStyle>({ ...DEFAULT, ...(job.style ?? {}) });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.fonts().then(setFonts).catch(() => setFonts([]));
  }, []);
  // 다른 작업을 고르거나 다시 만든 뒤에는 서버 값으로 맞춘다
  const saved: JobStyle = { ...DEFAULT, ...(job.style ?? {}) };
  const savedKey = JSON.stringify(saved);
  useEffect(() => {
    setDraft(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.job_id, savedKey]);

  const byKey = useMemo(() => Object.fromEntries(fonts.map((f) => [f.key, f])), [fonts]);
  const subFont: FontInfo | undefined = byKey[draft.subtitle_font];
  const titleFont: FontInfo | undefined = byKey[draft.title_font] ?? subFont;
  useEffect(() => {
    loadGoogleFont(subFont);
    loadGoogleFont(titleFont);
  }, [subFont, titleFont]);

  const drag = useRef<{ y: number; bottom: number } | null>(null);
  if (job.scenes.length === 0) return null;
  const locked = job.status === "queued" || job.status === "running";
  const changed = JSON.stringify(draft) !== savedKey;
  const set = <K extends keyof JobStyle>(k: K, v: JobStyle[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const clampBottom = (v: number) => Math.max(BOTTOM_MIN, Math.min(BOTTOM_MAX, BOTTOM_MIN + Math.round((v - BOTTOM_MIN) / 10) * 10));

  // 미리보기에서 자막을 위아래로 끌어 옮긴다 (화면 1px = 실제 영상 1/SCALE px)
  const onDragStart = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { y: e.clientY, bottom: draft.subtitle_bottom };
  };
  const onDragMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    set("subtitle_bottom", clampBottom(drag.current.bottom - (e.clientY - drag.current.y) / SCALE));
  };
  const onDragEnd = () => {
    drag.current = null;
  };

  const firstSub = job.scenes[0].subtitle_text ?? job.scenes[0].narration;
  const sample = wrapSample(firstSub, lineChars(draft.subtitle_size));
  const subCss = subFont?.css ?? DEFAULT_CSS;
  const titleCss = titleFont?.css ?? subCss;
  const title = draft.title_show ? job.title ?? "" : "";
  const heading = titleLayout(title, draft.title_size, true);
  const subtitle = subtitleLayout(draft.subtitle_size, draft.subtitle_bottom);
  const artworkTop = heading.top + heading.height;
  const artworkHeight = SAFE_HEIGHT - artworkTop - subtitle.space;

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
        <div className="block-head">
          <span className="sq" />
          <h2>자막 변경</h2>
        </div>
        <p className="style-target">
          적용할 영상 <b>{job.title ?? job.job_id}</b> <span className="muted">· {job.job_id}</span>
          <a href="#jobs" className="link-btn">다른 영상 고르기 ↓</a>
        </p>
        <div className="style-grid">
          <div className="style-controls">
            <label>
              <span>자막 글꼴 <b>{fonts.length}종</b> · 구글 폰트 {fonts.filter((f) => f.google).length} + 눈누 {fonts.filter((f) => f.url).length}</span>
              <select value={draft.subtitle_font} onChange={(e) => set("subtitle_font", e.target.value)}>
                <FontOptions fonts={fonts} />
              </select>
            </label>
            <label>
              <span>자막 크기 <b>{draft.subtitle_size}px</b> · 한 줄 약 {lineChars(draft.subtitle_size)}자</span>
              <input type="range" min={36} max={96} step={2} value={draft.subtitle_size}
                     onChange={(e) => set("subtitle_size", Number(e.target.value))} />
            </label>
            <div className="field">
              <span>자막 색상</span>
              <ColorPalette value={draft.subtitle_color} onChange={(c) => set("subtitle_color", c)} />
            </div>
            <label>
              <span>
                자막 위치 <b>아래에서 {draft.subtitle_bottom}px</b> · 미리보기의 자막을 끌어도 돼요
                {draft.subtitle_bottom !== BOTTOM_DEFAULT && (
                    <button type="button" className="link-btn" onClick={() => set("subtitle_bottom", BOTTOM_DEFAULT)}>기본값</button>
                )}
              </span>
              <span className="range-row">
                <small>아래</small>
                <input type="range" min={BOTTOM_MIN} max={BOTTOM_MAX} step={10} value={draft.subtitle_bottom}
                       onChange={(e) => set("subtitle_bottom", Number(e.target.value))} />
                <small>위</small>
              </span>
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
                      <FontOptions fonts={fonts} skipDefault />
                    </select>
                  </label>
                  <label>
                    <span>제목 크기 <b>{draft.title_size}px</b></span>
                    <input type="range" min={48} max={140} step={2} value={draft.title_size}
                           onChange={(e) => set("title_size", Number(e.target.value))} />
                  </label>
                  <div className="field">
                    <span>제목 색상</span>
                    <ColorPalette value={draft.title_color} onChange={(c) => set("title_color", c)} />
                  </div>
                </>
            )}
            {err && <p className="error-box">{err}</p>}
            <div className="scene-edit-foot">
              <span className="hint">
                {locked ? "영상을 만드는 중이에요" : changed ? "자막·합성만 다시 만들어요 (API 비용 없음)" : "지금 영상과 같아요"}
              </span>
              <button className="ghost" disabled={!changed || busy} onClick={() => setDraft(saved)}>되돌리기</button>
              <button className="cta" disabled={!changed || busy || locked} onClick={apply}>
                {busy ? "요청 중…" : "이 스타일로 다시 만들기 →"}
              </button>
            </div>
          </div>

          <div className="style-preview" style={{ width: W * SCALE, height: H * SCALE }} aria-label="자막 미리보기">
            <div className="sp-safe" style={{
              top: safeInsets.top * SCALE, right: safeInsets.right * SCALE,
              bottom: safeInsets.bottom * SCALE, left: safeInsets.left * SCALE,
            }}>
              <img className="sp-logo" src={logo} alt="스마트동스쿨" style={{ left: LOGO_LEFT * SCALE, width: LOGO_WIDTH * SCALE }} />
              {title && <div className="sp-title" style={{
                top: heading.top * SCALE, left: TEXT_PADDING * SCALE, right: TEXT_PADDING * SCALE,
                fontFamily: titleCss, fontSize: heading.size * SCALE, color: draft.title_color,
                lineHeight: TITLE_LINE_HEIGHT, WebkitLineClamp: heading.lines,
              }}>{title}</div>}
              <div className="sp-image" style={{
                top: artworkTop * SCALE, height: artworkHeight * SCALE, width: artworkHeight * 2 / 3 * SCALE,
              }}>그림 배치 영역</div>
              <div className="sp-sub"
                onPointerDown={onDragStart} onPointerMove={onDragMove} onPointerUp={onDragEnd} onPointerCancel={onDragEnd}
                title="위아래로 끌어서 위치를 바꿀 수 있어요"
                style={{
                  bottom: subtitle.offset * SCALE, left: TEXT_PADDING * SCALE, right: TEXT_PADDING * SCALE,
                  fontFamily: subCss, fontSize: draft.subtitle_size * SCALE, color: draft.subtitle_color,
                }}>{sample}</div>
            </div>
            <div className="sp-ui" style={{ height: safeInsets.bottom * SCALE }}>쇼츠·릴스·틱톡 UI 영역</div>
          </div>
        </div>
      </div>
  );
}
