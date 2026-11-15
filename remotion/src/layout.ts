export const VIDEO_WIDTH = 1080;
export const VIDEO_HEIGHT = 1920;
export const safeInsets = { top: 280, right: 252, bottom: 680, left: 108 };
export const SAFE_WIDTH = VIDEO_WIDTH - safeInsets.left - safeInsets.right;
export const SAFE_HEIGHT = VIDEO_HEIGHT - safeInsets.top - safeInsets.bottom;
export const TEXT_PADDING = 20;
export const TEXT_WIDTH = SAFE_WIDTH - TEXT_PADDING * 2;
export const LOGO_HEIGHT = 104;
export const LOGO_WIDTH = 200;
export const LOGO_LEFT = 8;
export const TITLE_LINE_HEIGHT = 1.2;
export const SUBTITLE_LINE_HEIGHT = 1.35;
export const DEFAULT_SUBTITLE_BOTTOM = safeInsets.bottom + 16;
export const MAX_SUBTITLE_BOTTOM = DEFAULT_SUBTITLE_BOTTOM + 100;

export function titleLayout(text: string, fontSize: number, hasLogo: boolean) {
  const units = [...text].reduce((width, char) =>
    width + (char === " " ? 0.35 : char.charCodeAt(0) < 128 ? 0.6 : 1), 0);
  const lines = units * fontSize <= TEXT_WIDTH ? 1 : 2;
  const unitsPerLine = lines === 1 ? units : Math.ceil(units / 2) + 1;
  const limit = lines === 1 ? fontSize : Math.min(110, fontSize);
  const size = Math.max(1, Math.min(limit, Math.floor(TEXT_WIDTH / Math.max(unitsPerLine, 1))));
  const top = hasLogo ? LOGO_HEIGHT : 0;
  const height = text ? Math.ceil(size * TITLE_LINE_HEIGHT * lines) + 20 : 0;
  return { size, top, height, lines };
}

export function subtitleLayout(fontSize: number, bottom: number) {
  const offset = Math.min(MAX_SUBTITLE_BOTTOM, Math.max(DEFAULT_SUBTITLE_BOTTOM, bottom)) - safeInsets.bottom;
  const height = Math.ceil(fontSize * SUBTITLE_LINE_HEIGHT * 2);
  return { offset, height, space: offset + height + 20 };
}

export function subtitleLineChars(fontSize: number) {
  return Math.max(1, Math.floor(TEXT_WIDTH / fontSize));
}
