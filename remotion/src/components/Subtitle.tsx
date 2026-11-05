import { AbsoluteFill } from "remotion";

// TODO: SRT 파싱 후 현재 프레임에 맞는 줄만 표시
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
        lineHeight: 1.35,
        textAlign: "center",
        wordBreak: "keep-all",
      }}
    >
      {text}
    </div>
  </AbsoluteFill>
);
