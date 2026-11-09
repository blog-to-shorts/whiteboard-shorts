import { AbsoluteFill } from "remotion";

export const Subtitle: React.FC<{ text: string }> = ({ text }) => (
  <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 220 }}>
    <div
      style={{
        maxWidth: 900,
        padding: "16px 28px",
        borderRadius: 12,
        background: "rgba(0,0,0,0.75)",
        color: "white",
        fontSize: 52,
        fontWeight: 700,
        fontFamily: 'system-ui, "Apple SD Gothic Neo", "Noto Sans CJK KR", sans-serif',
        whiteSpace: "pre-line",
        lineHeight: 1.35,
        textAlign: "center",
        wordBreak: "keep-all",
      }}
    >
      {text}
    </div>
  </AbsoluteFill>
);
