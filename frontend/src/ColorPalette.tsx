import { useEffect, useRef, useState } from "react";

// 파워포인트·워드의 색 선택창과 같은 배치: 테마 색 10개 + 각 색의 밝기 5단계 + 표준 색 10개
const THEME = ["#ffffff", "#000000", "#e7e6e6", "#44546a", "#4472c4", "#ed7d31", "#a5a5a5", "#ffc000", "#5b9bd5", "#70ad47"];
// THEME 각 열 아래로: 80%·60%·40% 밝게, 25%·50% 어둡게
const SHADES = [
  ["#f2f2f2", "#d9d9d9", "#bfbfbf", "#a6a6a6", "#808080"],
  ["#7f7f7f", "#595959", "#404040", "#262626", "#0d0d0d"],
  ["#d0cece", "#aeaaaa", "#757171", "#3a3838", "#171616"],
  ["#d6dce4", "#adb9ca", "#8496b0", "#333f4f", "#222a35"],
  ["#d9e2f3", "#b4c6e7", "#8eaadb", "#2f5496", "#1f3864"],
  ["#fbe5d5", "#f7cbac", "#f4b183", "#c55a11", "#833c0b"],
  ["#ededed", "#dbdbdb", "#c9c9c9", "#7b7b7b", "#525252"],
  ["#fff2cc", "#ffe599", "#ffd966", "#bf8f00", "#7f6000"],
  ["#deebf6", "#bdd7ee", "#9dc3e6", "#2e75b5", "#1f4e79"],
  ["#e2efd9", "#c5e0b3", "#a8d08d", "#538135", "#375623"],
];
const STANDARD = ["#c00000", "#ff0000", "#ffc000", "#ffff00", "#92d050", "#00b050", "#00b0f0", "#0070c0", "#002060", "#7030a0"];

function Chip({ color, value, onPick }: { color: string; value: string; onPick: (c: string) => void }) {
  return (
      <button type="button" className={`cp-chip${color === value.toLowerCase() ? " on" : ""}`}
              style={{ background: color }} title={color} aria-label={color} onClick={() => onPick(color)} />
  );
}

export function ColorPalette({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);

  // 바깥을 누르거나 Esc를 누르면 닫는다
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const pick = (c: string) => {
    onChange(c);
    setOpen(false);
  };

  return (
      <span className="cp" ref={box}>
        <button type="button" className="cp-trigger" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          <span className="cp-current" style={{ background: value }} />
          <code>{value}</code>
          <span className="cp-caret">▾</span>
        </button>
        {open && (
            <div className="cp-pop" role="dialog" aria-label="색 선택">
              <p className="cp-title">테마 색</p>
              <div className="cp-row">
                {THEME.map((c) => <Chip key={c} color={c} value={value} onPick={pick} />)}
              </div>
              <div className="cp-shades">
                {SHADES.map((col, i) => (
                    <div key={i} className="cp-col">
                      {col.map((c) => <Chip key={c} color={c} value={value} onPick={pick} />)}
                    </div>
                ))}
              </div>
              <p className="cp-title">표준 색</p>
              <div className="cp-row">
                {STANDARD.map((c) => <Chip key={c} color={c} value={value} onPick={pick} />)}
              </div>
              <label className="cp-more">
                <input type="color" value={value} onChange={(e) => onChange(e.target.value)} />
                <span>다른 색…</span>
              </label>
            </div>
        )}
      </span>
  );
}
