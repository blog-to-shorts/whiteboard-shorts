import { useState } from "react";

export function SketchIcon({ kind, className = "" }: { kind: "paper" | "pen" | "film"; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 120 120" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {kind === "paper" ? <>
        <path d="M28 17 81 14 99 33 95 104 24 100Z" /><path d="m81 14-1 22 19-3M38 49l42-2M37 61l35-1M37 73l40-1M37 85l25 1" />
        <path d="m10 37 7-3M8 52h7m84 21 10 3m-8-18 8-3" />
      </> : kind === "pen" ? <>
        <path d="m27 82 48-59q6-7 13-1l8 7q6 5 0 12L48 99l-26 9Z" /><path d="m27 82 21 17m-17-12-5 15 15-5m-2-16 46-55M69 31l21 18" />
        <path d="M16 47q-5-10 3-17m84 42 9-1M93 91l7 6M30 13l-3-9" />
      </> : <>
        <path d="m21 29 77-3 3 76-82 3Z" /><path d="m21 45 79-3M35 28l9 15m12-16 9 15m11-15 9 14M51 58l1 30 25-16Z" />
        <path d="m8 18 8 3M10 7l8 8m90 96 7 5m-11-14 11 1" />
      </>}
    </svg>
  );
}

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const links = [["#about", "서비스 소개"], ["#how", "사용 방법"], ["#faq", "자주 묻는 질문"], ["#team", "만든 사람들"]];
  return <header className="site-header">
    <a className="site-brand" href="#top" onClick={() => setOpen(false)}><SketchIcon kind="pen" />뚝딱쇼츠</a>
    <button className="menu-toggle" aria-expanded={open} aria-controls="site-navigation" onClick={() => setOpen(!open)}>{open ? "닫기 ×" : "메뉴 ☰"}</button>
    <nav id="site-navigation" className={`site-navigation${open ? " is-open" : ""}`} aria-label="주 메뉴">
      {links.map(([href, label]) => <a key={href} href={href} onClick={() => setOpen(false)}>{label}</a>)}
      <a className="nav-start" href="#create" onClick={() => setOpen(false)}>쇼츠 만들기 <span aria-hidden>↗</span></a>
    </nav>
  </header>;
}

export function HowItWorks() {
  const steps = [
    { kind: "paper" as const, title: "읽고 싶은 글을 넣고", description: "블로그 링크를 넣거나 원문을 붙여 넣으세요. 이야기의 시작은 글 한 편이면 충분해요." },
    { kind: "pen" as const, title: "그림과 목소리를 더해", description: "핵심을 대본으로 정리하고, 화이트보드 그림에 내레이션과 자막을 연결해요." },
    { kind: "film" as const, title: "나만의 쇼츠로 완성", description: "완성된 영상을 확인하고 MP4로 내려받으세요. 대본을 수정해 다시 만들 수도 있어요." },
  ];
  return <section className="home-section how-section" id="how" aria-labelledby="how-title">
    <p className="section-eyebrow">HOW IT WORKS / 사용 방법</p>
    <h2 id="how-title">긴 글이 짧은 영상이 되는 세 걸음.</h2>
    <div className="how-grid">{steps.map((step, i) => <article className="how-step" key={step.kind}>
      <div className="how-illustration"><SketchIcon kind={step.kind} /><span>0{i + 1}</span></div>
      <h3>{step.title}</h3><p>{step.description}</p>
    </article>)}</div>
  </section>;
}

export function FAQ() {
  const questions = [
    ["어떤 글을 넣으면 되나요?", "숏폼으로 전하고 싶은 블로그 글의 URL을 넣어주세요. 링크로 본문을 가져오기 어렵다면 ‘원문 직접 입력’에서 200자 이상의 글을 붙여 넣을 수 있어요."],
    ["완성된 영상은 어떤 형식인가요?", "화이트보드 일러스트, 내레이션, 자막이 결합된 9:16 세로형 영상이에요. 완성 후 MP4로 다운로드할 수 있어요."],
    ["생성된 대본을 수정할 수 있나요?", "영상 생성이 끝난 뒤, 아래 대본 영역에서 장면별 자막·읽는 문장·그림 설명을 수정하고 다시 만들 수 있어요. 생성 중에는 대본 수정이 잠시 제한돼요."],
    ["위쪽 소개 영상과 내가 만든 쇼츠는 다른가요?", "네! 첫 화면은 뚝딱쇼츠 서비스 소개 전용이에요. 직접 만든 영상과 진행 상태는 아래 ‘내가 만든 쇼츠’ 영역에서 확인할 수 있어요."],
  ];
  return <section className="home-section faq-section" id="faq" aria-labelledby="faq-title">
    <div><p className="section-eyebrow">FAQ / 자주 묻는 질문</p><h2 id="faq-title">궁금한 점을<br />뚝딱 풀어드려요.</h2><SketchIcon className="faq-drawing" kind="paper" /></div>
    <div className="faq-list">{questions.map(([q, a]) => <details key={q}><summary>{q}<span className="faq-plus" aria-hidden>+</span></summary><p>{a}</p></details>)}</div>
  </section>;
}

function TeamPortrait({ longHair, glasses, variant }: { longHair: boolean; glasses: boolean; variant: number }) {
  return <svg className="team-portrait" viewBox="0 0 160 170" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {longHair ? <>
      <path d="M36 125V64c0-27 16-40 44-40s44 13 44 40v61" />
      <path d="M48 63v20c0 20 13 32 32 32s32-12 32-32V63" />
      <path d={variant === 2 ? "M48 63q8-19 16-20l2 16 13-15 9 16 7-14 17 17" : variant === 4 ? "M48 63q27-2 42-24 3 19 22 24" : "M48 63q20-4 32-24 12 20 32 24"} />
    </> : <>
      <path d="M45 64c-1-24 13-37 35-37s36 13 35 37l-2 21c-2 18-14 30-33 30S49 103 47 85Z" />
      <path d={variant === 1 ? "M45 64q14-2 24-18l9 13 12-13q10 16 25 18" : "M45 64q20 0 30-19 12 18 40 19"} />
    </>}
    {glasses ? <>
      <rect x="52" y="69" width="23" height="18" rx="7" /><rect x="85" y="69" width="23" height="18" rx="7" /><path d="M75 76h10" />
      <path d="M63 77h1m32 0h1" strokeWidth="4" />
    </> : <path d="M62 77h1m34 0h1" strokeWidth="4" />}
    <path d="M70 96q10 9 20 0M68 114v12m24-12v12M32 152q3-24 36-26m24 0q33 2 36 26" />
  </svg>;
}
export function Team() {
  const members = [
    ["이지아", "통합 · 이식", "각자의 결과물을 하나의 흐름으로"],
    ["엄세훈", "대본", "이야기의 핵심을 정확하게"],
    ["김진선", "화풍 · 이미지", "한 장면씩, 일관된 그림으로"],
    ["홍영준", "TTS · 음성", "듣기 편안한 목소리로"],
    ["최민주", "웹 UI · 발표", "서비스의 첫인상부터 전달까지"],
  ];
  return <section className="home-section team-section" id="team" aria-labelledby="team-title">
    <p className="section-eyebrow">PEOPLE / 만든 사람들</p><h2 id="team-title">다섯 사람의 손길로, 뚝딱.</h2>
    <p className="team-intro">스마트동스쿨 기업 실무 프로젝트 · AI 서비스 개발 2조</p>
    <div className="team-grid">{members.map(([name, role, description], i) => <article className="team-member" key={name}>
      <span className="member-number">0{i + 1}</span>
      <TeamPortrait longHair={i === 0 || i === 2 || i === 4} glasses={name === "홍영준"} variant={i} />
      <h3>{name}</h3><p className="member-role">{role}</p><p>{description}</p>
      {name === "최민주" && <a className="member-email" href="mailto:0987cms@naver.com">0987cms@naver.com <span aria-hidden>↗</span></a>}
    </article>)}</div>
  </section>;
}

export function SiteFooter() {
  return <footer className="site-footer"><div><a href="#top">뚝딱쇼츠 <span aria-hidden>↗</span></a><p>당신의 블로그를 숏폼으로 그려드립니다.</p></div><p>스마트동스쿨 기업 실무 프로젝트<br />AI 서비스 개발 2조</p></footer>;
}
