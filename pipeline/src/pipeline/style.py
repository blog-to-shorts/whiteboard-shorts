"""영상마다 다른 자막·제목 모양.

기본값은 .env(SUBTITLE_*, TITLE_*) → config.py이고, 웹에서 고른 값은 jobs/<id>/style.json에 저장돼 기본값을 덮어쓴다.
s07(자막 줄바꿈 글자 수)과 s08(Remotion props)이 같은 값을 읽는다.
"""
import json
from pathlib import Path

from .config import settings

STYLE_FILE = "style.json"

# 웹에서 고를 수 있는 글꼴. css: Remotion·브라우저에 넘길 font-family, google: 구글 폰트 이름(없으면 PC에 깔린 글꼴)
FONTS: dict[str, dict] = {
    "malgun": {"label": "맑은 고딕 (기본)", "css": "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif"},
    "noto-sans": {"label": "Noto Sans KR", "css": "'Noto Sans KR', sans-serif", "google": "Noto Sans KR"},
    "nanum-gothic": {"label": "나눔고딕", "css": "'Nanum Gothic', sans-serif", "google": "Nanum Gothic"},
    "gothic-a1": {"label": "Gothic A1", "css": "'Gothic A1', sans-serif", "google": "Gothic A1"},
    "nanum-myeongjo": {"label": "나눔명조", "css": "'Nanum Myeongjo', serif", "google": "Nanum Myeongjo"},
    "black-han-sans": {"label": "검은고딕 (Black Han Sans)", "css": "'Black Han Sans', sans-serif", "google": "Black Han Sans"},
    "do-hyeon": {"label": "도현", "css": "'Do Hyeon', sans-serif", "google": "Do Hyeon"},
    "jua": {"label": "주아", "css": "'Jua', sans-serif", "google": "Jua"},
    "gowun-dodum": {"label": "고운돋움", "css": "'Gowun Dodum', sans-serif", "google": "Gowun Dodum"},
    "nanum-pen": {"label": "나눔손글씨 펜", "css": "'Nanum Pen Script', cursive", "google": "Nanum Pen Script"},
}

SUBTITLE_SIZE_RANGE = (36, 96)
TITLE_SIZE_RANGE = (48, 140)


def defaults() -> dict:
    return {
        "subtitle_font": "",  # 빈 값 = .env의 SUBTITLE_FONT
        "subtitle_size": settings.subtitle_size,
        "title_show": settings.title_show,
        "title_font": "",     # 빈 값 = 자막 글꼴과 같게
        "title_size": settings.title_size,
    }


def load(job_dir: Path) -> dict:
    """기본값 + 이 job에서 고른 값"""
    style = defaults()
    try:
        saved = json.loads((job_dir / STYLE_FILE).read_text(encoding="utf-8"))
        style.update({k: v for k, v in saved.items() if k in style and v is not None})
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return style


def save(job_dir: Path, style: dict) -> dict:
    merged = defaults()
    merged.update({k: v for k, v in style.items() if k in merged and v is not None})
    for key in ("subtitle_font", "title_font"):
        if merged[key] and merged[key] not in FONTS:
            raise ValueError(f"모르는 글꼴입니다: {merged[key]}")
    lo, hi = SUBTITLE_SIZE_RANGE
    merged["subtitle_size"] = max(lo, min(hi, int(merged["subtitle_size"])))
    lo, hi = TITLE_SIZE_RANGE
    merged["title_size"] = max(lo, min(hi, int(merged["title_size"])))
    merged["title_show"] = bool(merged["title_show"])
    (job_dir / STYLE_FILE).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def font_css(key: str, fallback: str) -> str:
    return FONTS[key]["css"] if key in FONTS else fallback


def line_chars(subtitle_size: int) -> int:
    """자막 한 줄 글자 수. 1080px 폭에서 글씨 56일 때 19자 기준으로 비례"""
    return max(8, round(19 * 56 / subtitle_size))


def remotion_style(job_dir: Path) -> dict:
    """s08이 Remotion props.style로 넘기는 값"""
    st = load(job_dir)
    sub_font = font_css(st["subtitle_font"], settings.subtitle_font)
    title_font = font_css(st["title_font"], settings.title_font or sub_font)
    return {
        "subtitle": {
            "font": sub_font,
            "size": st["subtitle_size"],
            "weight": settings.subtitle_weight,
            "color": settings.subtitle_color,
            "bottom": settings.subtitle_bottom,
        },
        "title": {
            "font": title_font,
            "size": st["title_size"],
            "color": settings.title_color,
            "top": settings.title_top,
        },
    }
