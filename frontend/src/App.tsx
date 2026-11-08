import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api, Job, JobStatus, STEP_LABELS, STEP_ORDER } from "./api";

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
  }, [selectedId]);

  const latestDone = jobs.find((j) => j.status === "done") ?? null;
  const running = jobs.find((j) => j.status === "running") ?? null;
  const doneCount = jobs.filter((j) => j.status === "done").length;

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

      {/* ---------- 새 영상 ---------- */}
      <section className="block create-block" id="create">
        <div className="block-head">
          <span className="sq" />
          <h2>New Short<sup>{"{01}"}</sup></h2>
        </div>
        <CreateForm onCreated={onCreated} onError={setError} />
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
        {selected && <Script job={selected} />}
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

function Script({ job }: { job: Job }) {
  if (job.scenes.length === 0) return null;
  return (
    <div className="script">
      <h3><span className="sq" />Script<sup>{`{${pad(job.scenes.length)}}`}</sup></h3>
      <ol>
        {job.scenes.map((s) => (
          <Fragment key={s.id}>
            <li>
              <span className="num">{`{${pad(s.id)}}`}</span>
              <p>{s.subtitle_text ?? s.narration}</p>
              <span className="muted small">{s.duration != null ? `${s.duration.toFixed(1)}s` : ""}</span>
            </li>
          </Fragment>
        ))}
      </ol>
    </div>
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
