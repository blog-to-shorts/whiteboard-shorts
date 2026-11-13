import { useCallback, useEffect, useMemo, useState } from "react";
import { StylePanel } from "./StylePanel";
import { api, Job, JobStatus, Scene, STEP_LABELS, STEP_ORDER } from "./api";

// ---------- 사이트 이름: 여기만 바꾸면 워드마크·탭 제목이 함께 바뀐다 ----------
// pixel: 픽셀 글꼴로 바꿔 쓸 글자의 위치 (0부터)
const BRAND = {
  top: { word: "SKETCH", pixel: [2, 4] },
  bottom: { word: "SHORTS", pixel: [2] },
  role: "Blog-to-Shorts Pipeline",
};

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "대기 중",
  running: "생성 중",
  done: "완료",
  error: "실패",
};

const pad = (n: number) => String(n).padStart(2, "0");
const fmtSec = (s: number | null | undefined) =>
    s == null ? "-" : s >= 60 ? `${Math.floor(s / 60)}분 ${Math.round(s % 60)}초` : `${s.toFixed(1)}초`;

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0); // 장면을 다시 만들면 올려서 상태 갱신을 다시 시작

  useEffect(() => {
    document.title = `${cap(BRAND.top.word)} ${cap(BRAND.bottom.word)}`;
  }, []);

  const refreshList = useCallback(async () => {
    try {
      const list = await api.list();
      setJobs(list);
      setSelectedId((cur) => cur ?? list.find((j) => j.status === "done")?.job_id ?? list[0]?.job_id ?? null);
    } catch (e) {
      setError(`서버에 연결할 수 없습니다. FastAPI가 켜져 있는지 확인하세요. (${(e as Error).message})`);
    }
  }, []);

  // 목록: 처음 한 번 + 진행 중인 작업이 있으면 3초마다
  const active = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    refreshList();
  }, [refreshList]);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(refreshList, 3000);
    return () => clearInterval(t);
  }, [active, refreshList]);

  // 선택한 작업: 진행 중이면 2초마다 상태 갱신
  useEffect(() => {
    if (!selectedId) return setSelected(null);
    let stop = false;
    const load = async () => {
      try {
        const j = await api.get(selectedId);
        if (!stop) setSelected(j);
        return j;
      } catch {
        return null;
      }
    };
    load();
    const t = setInterval(async () => {
      const j = await load();
      if (j && (j.status === "done" || j.status === "error")) clearInterval(t);
    }, 2000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [selectedId, reloadKey]);

  const latestDone = jobs.find((j) => j.status === "done") ?? null;
  const running = jobs.find((j) => j.status === "running") ?? null;
  const doneCount = jobs.filter((j) => j.status === "done").length;

  const onRerun = async () => {
    setReloadKey((k) => k + 1);
    await refreshList();
  };

  const onCreated = async (ids: string[]) => {
    setError(null);
    setSelectedId(ids[0]);
    await refreshList();
    document.getElementById("jobs")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
      <div className="app">
        <div className="grain" aria-hidden />

        {/* ---------- 히어로: 거대한 워드마크 + 겹친 영상 ---------- */}
        <section className="hero" id="top">
          <Wordmark {...BRAND.top} className="wm-top" />
          <div className="hero-media">
            {latestDone && api.videoUrl(latestDone) ? (
                <video src={api.videoUrl(latestDone)!} autoPlay muted loop playsInline />
            ) : (
                <div className="hero-media-empty">첫 영상을 만들면 여기서 재생돼요</div>
            )}
            {latestDone && <span className="media-tag">{latestDone.title}</span>}
          </div>
          <Wordmark {...BRAND.bottom} className="wm-bottom" />
          <span className="sq hero-sq" />
          <p className="hero-tagline">
            블로그 글 하나를 넣으면 대본, 그림, 내레이션, 드로잉, 자막까지 자동으로 이어 붙여 30~60초 화이트보드 숏폼을 만듭니다.
          </p>
        </section>

        {error && <div className="banner" onClick={() => setError(null)}>{error}</div>}

        {/* ---------- 새 영상 + 자막 스타일 (선택한 영상) ---------- */}
        <section className="block create-block" id="create">
          <div className="create-split">
            <div>
              <div className="block-head">
                <span className="sq" />
                <h2>New Short<sup>{"{01}"}</sup></h2>
              </div>
              <CreateForm onCreated={onCreated} onError={setError} />
            </div>
            {selected && <StylePanel job={selected} onApplied={onRerun} />}
          </div>
        </section>

        {/* ---------- 작업: 가운데 세로 영상 + 양옆 라벨 ---------- */}
        <section className="block jobs-block" id="jobs">
          <div className="corner-label"><span className="sq" /> {`{01—${pad(jobs.length)}}`}</div>
          <div className="stage">
            <div className="stage-side left">
              <h2><span className="sq" />Selected Job<sup>{selected ? `{${selected.job_id.slice(-2)}}` : "{—}"}</sup></h2>
              {selected && <JobMeta job={selected} />}
            </div>
            <div className="stage-center">
              <Player job={selected} />
            </div>
            <div className="stage-side right">
              <h2>All Jobs<sup>{`{${pad(jobs.length)}}`}</sup></h2>
              <JobList jobs={jobs} selectedId={selectedId} onSelect={setSelectedId} />
            </div>
          </div>
          {selected && <Script job={selected} onRerun={onRerun} />}
        </section>

        {/* ---------- 포인트 컬러 섹션 ---------- */}
        <section className="block accent-block" id="about">
          <h2 className="statement">
            블로그 한 편이 사람 손을 거치지 않고, 2분 안에 직접 그려지는 숏폼이 됩니다.
          </h2>
          <div className="about-grid">
            <dl className="about-stats">
              <div><dt>자동 단계</dt><dd>{"{08}"}</dd></div>
              <div><dt>완성 영상</dt><dd>{`{${pad(doneCount)}}`}</dd></div>
              <div><dt>출력</dt><dd>{"{1080×1920}"}</dd></div>
            </dl>
            <div className="about-cols">
              <p>
                본문을 추출하고 핵심 정보를 뽑은 뒤, 장면마다 TTS용 문장과 자막용 문장을 나눠 대본을 씁니다.
                핵심 포인트가 빠지거나 길이가 30~60초를 벗어나면 코드가 잡아내 다시 만듭니다.
              </p>
              <p>
                음성을 먼저 만들어 실제 길이를 확인한 뒤 흑백 화이트보드 그림을 생성하고, 그림이 음성에 맞춰
                그려지는 드로잉 영상으로 바꿉니다. 마지막으로 자막을 얹어 세로형 MP4로 렌더링합니다.
              </p>
            </div>
          </div>
        </section>

        {/* ---------- 하단 고정 메뉴 ---------- */}
        <nav className="dock">
          <span className="dock-role"><span className="logo-px" /> {BRAND.role}</span>
          <span className="dock-links">
          <a href="#create">Create,</a> <a href="#jobs">Jobs,</a> <a href="#about">About</a>
        </span>
          <a className="dock-contact" href="http://localhost:8000/docs" target="_blank" rel="noreferrer">API Docs</a>
        </nav>

        {/* 진행 중인 작업 미니 카드 (시안의 오른쪽 아래 썸네일 자리) */}
        {running && (
            <button className="mini" onClick={() => { setSelectedId(running.job_id); document.getElementById("jobs")?.scrollIntoView({ behavior: "smooth" }); }}>
              <span className="mini-dot" />
              <span>
            <b>{running.title ?? "새 영상"}</b>
            <small>{running.current_step ? STEP_LABELS[running.current_step] : "준비 중"}</small>
          </span>
            </button>
        )}
      </div>
  );
}

function Wordmark({ word, pixel, className }: { word: string; pixel: number[]; className: string }) {
  return (
      <h1 className={`wordmark ${className}`} aria-label={word}>
        {word.split("").map((ch, i) => (
            <span key={i} className={pixel.includes(i) ? "px" : undefined}>{ch}</span>
        ))}
      </h1>
  );
}

function CreateForm({ onCreated, onError }: { onCreated: (ids: string[]) => void; onError: (m: string) => void }) {
  const [mode, setMode] = useState<"url" | "text">("url");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const urls = useMemo(
      () => value.split(/\n+/).map((s) => s.trim()).filter((s) => /^https?:\/\//.test(s)),
      [value],
  );
  const canSubmit = !busy && (mode === "url" ? urls.length > 0 : value.trim().length >= 200);

  const submit = async () => {
    setBusy(true);
    try {
      const r = mode === "url" ? await api.create(urls) : await api.createFromText(value.trim());
      setValue("");
      onCreated(r.job_ids);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
      <div className="create">
        <div className="tabs">
          <button className={mode === "url" ? "on" : ""} onClick={() => setMode("url")}>Blog URL,</button>
          <button className={mode === "text" ? "on" : ""} onClick={() => setMode("text")}>원문 직접 입력</button>
        </div>
        <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={
              mode === "url"
                  ? "https://blog.naver.com/…\n여러 줄로 넣으면 순서대로 일괄 생성돼요"
                  : "URL로 본문을 가져오지 못할 때 원문을 붙여 넣으세요 (200자 이상)"
            }
            rows={mode === "url" ? 3 : 7}
        />
        <div className="create-foot">
        <span className="hint">
          {mode === "url"
              ? urls.length > 1 ? `{${pad(urls.length)}} URL · 일괄 생성` : urls.length === 1 ? "{01} URL" : "URL을 입력하세요"
              : `${value.trim().length}자`}
        </span>
          <button className="cta" disabled={!canSubmit} onClick={submit}>
            {busy ? "요청 중…" : mode === "url" && urls.length > 1 ? `${urls.length}개 생성 →` : "영상 생성 →"}
          </button>
        </div>
      </div>
  );
}

function JobList({ jobs, selectedId, onSelect }: { jobs: Job[]; selectedId: string | null; onSelect: (id: string) => void }) {
  if (jobs.length === 0) return <p className="muted">아직 만든 영상이 없어요.</p>;
  return (
      <ul className="joblist">
        {jobs.map((j, i) => (
            <li key={j.job_id} className={j.job_id === selectedId ? "sel" : ""} onClick={() => onSelect(j.job_id)}>
              <span className="idx">{pad(jobs.length - i)}</span>
              <span className="jl-title">{j.title ?? shortUrl(j.source_url ?? j.job_id)}</span>
              <Badge job={j} />
            </li>
        ))}
      </ul>
  );
}

function Badge({ job }: { job: Job }) {
  const extra =
      job.status === "queued" && job.queue_position
          ? ` ${job.queue_position}번째`
          : job.status === "running" && job.current_step
              ? ` · ${STEP_LABELS[job.current_step] ?? job.current_step}`
              : "";
  return <span className={`badge ${job.status}`}>{STATUS_LABEL[job.status]}{extra}</span>;
}

function JobMeta({ job }: { job: Job }) {
  const byStep = Object.fromEntries(job.steps.map((s) => [s.step, s]));
  return (
      <div className="meta">
        <p className="meta-title">{job.title ?? "제목 생성 전"}</p>
        {job.source_url && (
            <a className="muted small" href={job.source_url} target="_blank" rel="noreferrer">{shortUrl(job.source_url)} ↗</a>
        )}
        <Badge job={job} />
        <ol className="steps">
          {STEP_ORDER.map((key, i) => {
            const s = byStep[key];
            const st = s?.status ?? (job.status === "done" ? "done" : "todo");
            return (
                <li key={key} className={st}>
                  <span className="step-no">{pad(i + 1)}</span>
                  <span className="step-label">{STEP_LABELS[key]}</span>
                  <span className="step-sec">{s?.seconds != null && st === "done" ? `${s.seconds.toFixed(1)}s` : st === "running" ? "…" : ""}</span>
                </li>
            );
          })}
        </ol>
        {job.status === "error" && <p className="error-box">실패 원인: {job.error ?? "알 수 없음"}</p>}
        <dl className="stats">
          <div><dt>영상 길이</dt><dd>{fmtSec(job.duration)}</dd></div>
          <div><dt>처리 시간</dt><dd>{fmtSec(job.total_seconds)}</dd></div>
          <div><dt>장면</dt><dd>{job.scenes.length || "-"}</dd></div>
        </dl>
      </div>
  );
}

function Player({ job }: { job: Job | null }) {
  const video = job ? api.videoUrl(job) : null;
  return (
      <div className="player">
        {video ? (
            <video key={video} src={video} controls playsInline />
        ) : (
            <div className="placeholder">
              {!job ? "작업을 고르세요" : job.status === "error" ? "영상을 만들지 못했어요" : "영상을 그리는 중이에요…"}
            </div>
        )}
        {video && <a className="cta block" href={api.downloadUrl(job!)!}>MP4 다운로드 ↓</a>}
      </div>
  );
}

function Script({ job, onRerun }: { job: Job; onRerun: () => void }) {
  if (job.scenes.length === 0) return null;
  // 실행 중이거나 대기 중일 때는 수정할 수 없다
  const locked = job.status === "queued" || job.status === "running";
  return (
      <div className="script">
        <h3><span className="sq" />Script<sup>{`{${pad(job.scenes.length)}}`}</sup></h3>
        {locked && <p className="muted small">영상을 만드는 중에는 대본을 고칠 수 없어요.</p>}
        <ol>
          {job.scenes.map((s) => (
              <SceneRow key={s.id} jobId={job.job_id} scene={s} locked={locked} onRerun={onRerun} />
          ))}
        </ol>
      </div>
  );
}

type Draft = { narration: string; subtitle_text: string; image_prompt: string };

// 바뀐 항목에 따라 다시 만드는 범위 (백엔드 rerun과 같은 기준)
function rerunScope(scene: Scene, d: Draft) {
  const voice = d.narration.trim() !== scene.narration;
  const image = d.image_prompt.trim() !== (scene.image_prompt ?? "");
  const sub = d.subtitle_text.trim() !== (scene.subtitle_text ?? scene.narration);
  if (voice && image) return "그림·음성부터";
  if (image) return "그림부터";
  if (voice) return "음성부터";
  if (sub) return "영상 합성만";
  return null;
}

function SceneRow({ jobId, scene, locked, onRerun }: { jobId: string; scene: Scene; locked: boolean; onRerun: () => void }) {
  const initial = (): Draft => ({
    narration: scene.narration,
    subtitle_text: scene.subtitle_text ?? scene.narration,
    image_prompt: scene.image_prompt ?? "",
  });
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // 다시 만든 뒤 서버의 새 대본으로 편집 칸을 맞춘다 (편집 중이 아닐 때만)
  useEffect(() => {
    if (!open) setDraft(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.narration, scene.subtitle_text, scene.image_prompt, open]);

  const scope = rerunScope(scene, draft);
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLTextAreaElement>) => setDraft({ ...draft, [k]: e.target.value });

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.rerun(jobId, [{ id: scene.id, ...draft }]);
      setOpen(false);
      onRerun();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
      <li className={open ? "editing" : undefined}>
        <span className="num">{`{${pad(scene.id)}}`}</span>
        <div className="scene-text">
          <p>{scene.subtitle_text ?? scene.narration}</p>
          {open && (
              <div className="scene-edit">
                <label>
                  <span>자막 (화면에 보이는 문장)</span>
                  <textarea rows={2} value={draft.subtitle_text} onChange={set("subtitle_text")} />
                </label>
                <label>
                  <span>읽는 문장 (숫자·영문 약어는 한글로: 60점 → 육십점)</span>
                  <textarea rows={2} value={draft.narration} onChange={set("narration")} />
                </label>
                <label>
                  <span>그림 설명 (영어, 그림 속 글자 금지)</span>
                  <textarea rows={3} value={draft.image_prompt} onChange={set("image_prompt")} />
                </label>
                {err && <p className="error-box">{err}</p>}
                <div className="scene-edit-foot">
                  <span className="hint">{scope ? `${scope} 다시 만들어요` : "바뀐 내용이 없어요"}</span>
                  <button className="ghost" onClick={() => { setOpen(false); setDraft(initial()); setErr(null); }}>취소</button>
                  <button className="cta" disabled={!scope || busy || locked} onClick={submit}>
                    {busy ? "요청 중…" : "이 장면 다시 만들기 →"}
                  </button>
                </div>
              </div>
          )}
        </div>
        <span className="scene-side">
        <span className="muted small">{scene.duration != null ? `${scene.duration.toFixed(1)}s` : ""}</span>
          {!open && (
              <button className="edit-btn" disabled={locked} onClick={() => setOpen(true)}>수정</button>
          )}
      </span>
      </li>
  );
}

function cap(w: string) {
  return w.charAt(0) + w.slice(1).toLowerCase();
}

function shortUrl(u: string) {
  try {
    const url = new URL(u);
    return url.hostname.replace(/^www\./, "") + url.pathname;
  } catch {
    return u;
  }
}