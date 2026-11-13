"""영상마다 다른 자막·제목 모양.

기본값은 .env(SUBTITLE_*, TITLE_*) → config.py이고, 웹에서 고른 값은 jobs/<id>/style.json에 저장돼 기본값을 덮어쓴다.
s07(자막 줄바꿈 글자 수)과 s08(Remotion props)이 같은 값을 읽는다.
"""
import json
import re
from pathlib import Path

from .config import settings

STYLE_FILE = "style.json"

# 웹에서 고를 수 있는 글꼴 (구글 폰트 중 한글 지원, 모두 불러오기 확인함).
# css: Remotion·브라우저에 넘길 font-family / google: 구글 폰트 CSS2 family 값(굵기 포함, 없으면 PC 글꼴) / group: 웹 목록 묶음
FONTS: dict[str, dict] = {
    "malgun": {"label": "맑은 고딕 (기본)", "group": "고딕", "css": "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif", "google": None},
    "noto-sans": {"label": "Noto Sans KR", "group": "고딕", "css": "'Noto Sans KR', sans-serif", "google": "Noto+Sans+KR:wght@400;700;900"},
    "nanum-gothic": {"label": "나눔고딕", "group": "고딕", "css": "'Nanum Gothic', sans-serif", "google": "Nanum+Gothic:wght@400;700;800"},
    "gothic-a1": {"label": "Gothic A1", "group": "고딕", "css": "'Gothic A1', sans-serif", "google": "Gothic+A1:wght@400;700;900"},
    "ibm-plex": {"label": "IBM Plex Sans KR", "group": "고딕", "css": "'IBM Plex Sans KR', sans-serif", "google": "IBM+Plex+Sans+KR:wght@400;700"},
    "gowun-dodum": {"label": "고운돋움", "group": "고딕", "css": "'Gowun Dodum', sans-serif", "google": "Gowun+Dodum"},
    "sunflower": {"label": "해바라기 (Sunflower)", "group": "고딕", "css": "'Sunflower', sans-serif", "google": "Sunflower:wght@300;500;700"},
    "orbit": {"label": "Orbit", "group": "고딕", "css": "'Orbit', sans-serif", "google": "Orbit"},
    "noto-serif": {"label": "Noto Serif KR", "group": "명조", "css": "'Noto Serif KR', serif", "google": "Noto+Serif+KR:wght@400;700;900"},
    "nanum-myeongjo": {"label": "나눔명조", "group": "명조", "css": "'Nanum Myeongjo', serif", "google": "Nanum+Myeongjo:wght@400;700;800"},
    "gowun-batang": {"label": "고운바탕", "group": "명조", "css": "'Gowun Batang', serif", "google": "Gowun+Batang:wght@400;700"},
    "hahmlet": {"label": "함렛 (Hahmlet)", "group": "명조", "css": "'Hahmlet', serif", "google": "Hahmlet:wght@400;700;900"},
    "song-myung": {"label": "송명", "group": "명조", "css": "'Song Myung', serif", "google": "Song+Myung"},
    "diphylleia": {"label": "Diphylleia", "group": "명조", "css": "'Diphylleia', serif", "google": "Diphylleia"},
    "black-han-sans": {"label": "검은고딕 (Black Han Sans)", "group": "제목용", "css": "'Black Han Sans', sans-serif", "google": "Black+Han+Sans"},
    "do-hyeon": {"label": "도현", "group": "제목용", "css": "'Do Hyeon', sans-serif", "google": "Do+Hyeon"},
    "jua": {"label": "주아", "group": "제목용", "css": "'Jua', sans-serif", "google": "Jua"},
    "gugi": {"label": "구기", "group": "제목용", "css": "'Gugi', sans-serif", "google": "Gugi"},
    "gasoek-one": {"label": "가석 (Gasoek One)", "group": "제목용", "css": "'Gasoek One', sans-serif", "google": "Gasoek+One"},
    "bagel-fat-one": {"label": "Bagel Fat One", "group": "제목용", "css": "'Bagel Fat One', sans-serif", "google": "Bagel+Fat+One"},
    "stylish": {"label": "스타일리시", "group": "제목용", "css": "'Stylish', sans-serif", "google": "Stylish"},
    "yeon-sung": {"label": "연성", "group": "제목용", "css": "'Yeon Sung', sans-serif", "google": "Yeon+Sung"},
    "dongle": {"label": "동글", "group": "제목용", "css": "'Dongle', sans-serif", "google": "Dongle:wght@400;700"},
    "moirai-one": {"label": "Moirai One", "group": "제목용", "css": "'Moirai One', sans-serif", "google": "Moirai+One"},
    "black-and-white": {"label": "흑백사진 (Black And White Picture)", "group": "제목용", "css": "'Black And White Picture', sans-serif", "google": "Black+And+White+Picture"},
    "nanum-pen": {"label": "나눔손글씨 펜", "group": "손글씨", "css": "'Nanum Pen Script', cursive", "google": "Nanum+Pen+Script"},
    "nanum-brush": {"label": "나눔손글씨 붓", "group": "손글씨", "css": "'Nanum Brush Script', cursive", "google": "Nanum+Brush+Script"},
    "gaegu": {"label": "개구", "group": "손글씨", "css": "'Gaegu', cursive", "google": "Gaegu:wght@400;700"},
    "gamja-flower": {"label": "감자꽃", "group": "손글씨", "css": "'Gamja Flower', cursive", "google": "Gamja+Flower"},
    "hi-melody": {"label": "하이멜로디", "group": "손글씨", "css": "'Hi Melody', cursive", "google": "Hi+Melody"},
    "poor-story": {"label": "푸어스토리", "group": "손글씨", "css": "'Poor Story', cursive", "google": "Poor+Story"},
    "cute-font": {"label": "귀여운 글꼴 (Cute Font)", "group": "손글씨", "css": "'Cute Font', cursive", "google": "Cute+Font"},
    "single-day": {"label": "싱글데이", "group": "손글씨", "css": "'Single Day', cursive", "google": "Single+Day"},
    "kirang-haerang": {"label": "기랑해랑", "group": "손글씨", "css": "'Kirang Haerang', cursive", "google": "Kirang+Haerang"},
    "dokdo": {"label": "독도", "group": "손글씨", "css": "'Dokdo', cursive", "google": "Dokdo"},
    "east-sea-dokdo": {"label": "동해독도", "group": "손글씨", "css": "'East Sea Dokdo', cursive", "google": "East+Sea+Dokdo"},
}

SUBTITLE_SIZE_RANGE = (36, 96)
TITLE_SIZE_RANGE = (48, 140)


def defaults() -> dict:
    return {
        "subtitle_font": "",  # 빈 값 = .env의 SUBTITLE_FONT
        "subtitle_size": settings.subtitle_size,
        "subtitle_color": settings.subtitle_color,
        "title_show": settings.title_show,
        "title_font": "",     # 빈 값 = 자막 글꼴과 같게
        "title_size": settings.title_size,
        "title_color": settings.title_color,
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
    for key in ("subtitle_color", "title_color"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(merged[key])):
            raise ValueError(f"색상은 #RRGGBB 형식이어야 합니다: {merged[key]}")
        merged[key] = merged[key].lower()
    (job_dir / STYLE_FILE).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def font_css(key: str, fallback: str) -> str:
    return FONTS[key]["css"] if key in FONTS else fallback


def google_spec(key: str) -> str:
    """Remotion이 렌더 전에 불러올 구글 폰트 (빈 값이면 PC 글꼴)"""
    return (FONTS.get(key) or {}).get("google") or ""


def line_chars(subtitle_size: int) -> int:
    """자막 한 줄 글자 수. 1080px 폭에서 글씨 56일 때 19자 기준으로 비례"""
    return max(8, round(19 * 56 / subtitle_size))


def remotion_style(job_dir: Path) -> dict:
    """s08이 Remotion props.style로 넘기는 값"""
    st = load(job_dir)
    sub_font = font_css(st["subtitle_font"], settings.subtitle_font)
    title_key = st["title_font"] or st["subtitle_font"]
    title_font = font_css(title_key, settings.title_font or sub_font)
    return {
        "subtitle": {
            "font": sub_font,
            "size": st["subtitle_size"],
            "weight": settings.subtitle_weight,
            "color": st["subtitle_color"],
            "bottom": settings.subtitle_bottom,
            "google": google_spec(st["subtitle_font"]),
        },
        "title": {
            "font": title_font,
            "size": st["title_size"],
            "color": st["title_color"],
            "top": settings.title_top,
            "google": google_spec(title_key),
        },
    }
