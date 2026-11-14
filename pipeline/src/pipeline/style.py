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
    "malgun": {"label": "맑은 고딕 (기본)", "group": "기본", "css": "'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif", "google": None},
    "noto-sans": {"label": "Noto Sans KR", "group": "구글 · 고딕", "css": "'Noto Sans KR', sans-serif", "google": "Noto+Sans+KR:wght@400;700;900"},
    "nanum-gothic": {"label": "나눔고딕", "group": "구글 · 고딕", "css": "'Nanum Gothic', sans-serif", "google": "Nanum+Gothic:wght@400;700;800"},
    "gothic-a1": {"label": "Gothic A1", "group": "구글 · 고딕", "css": "'Gothic A1', sans-serif", "google": "Gothic+A1:wght@400;700;900"},
    "ibm-plex": {"label": "IBM Plex Sans KR", "group": "구글 · 고딕", "css": "'IBM Plex Sans KR', sans-serif", "google": "IBM+Plex+Sans+KR:wght@400;700"},
    "gowun-dodum": {"label": "고운돋움", "group": "구글 · 고딕", "css": "'Gowun Dodum', sans-serif", "google": "Gowun+Dodum"},
    "sunflower": {"label": "해바라기 (Sunflower)", "group": "구글 · 고딕", "css": "'Sunflower', sans-serif", "google": "Sunflower:wght@300;500;700"},
    "orbit": {"label": "Orbit", "group": "구글 · 고딕", "css": "'Orbit', sans-serif", "google": "Orbit"},
    "noto-serif": {"label": "Noto Serif KR", "group": "구글 · 명조", "css": "'Noto Serif KR', serif", "google": "Noto+Serif+KR:wght@400;700;900"},
    "nanum-myeongjo": {"label": "나눔명조", "group": "구글 · 명조", "css": "'Nanum Myeongjo', serif", "google": "Nanum+Myeongjo:wght@400;700;800"},
    "gowun-batang": {"label": "고운바탕", "group": "구글 · 명조", "css": "'Gowun Batang', serif", "google": "Gowun+Batang:wght@400;700"},
    "hahmlet": {"label": "함렛 (Hahmlet)", "group": "구글 · 명조", "css": "'Hahmlet', serif", "google": "Hahmlet:wght@400;700;900"},
    "song-myung": {"label": "송명", "group": "구글 · 명조", "css": "'Song Myung', serif", "google": "Song+Myung"},
    "diphylleia": {"label": "Diphylleia", "group": "구글 · 명조", "css": "'Diphylleia', serif", "google": "Diphylleia"},
    "black-han-sans": {"label": "검은고딕 (Black Han Sans)", "group": "구글 · 제목용", "css": "'Black Han Sans', sans-serif", "google": "Black+Han+Sans"},
    "do-hyeon": {"label": "도현", "group": "구글 · 제목용", "css": "'Do Hyeon', sans-serif", "google": "Do+Hyeon"},
    "jua": {"label": "주아", "group": "구글 · 제목용", "css": "'Jua', sans-serif", "google": "Jua"},
    "gugi": {"label": "구기", "group": "구글 · 제목용", "css": "'Gugi', sans-serif", "google": "Gugi"},
    "gasoek-one": {"label": "가석 (Gasoek One)", "group": "구글 · 제목용", "css": "'Gasoek One', sans-serif", "google": "Gasoek+One"},
    "bagel-fat-one": {"label": "Bagel Fat One", "group": "구글 · 제목용", "css": "'Bagel Fat One', sans-serif", "google": "Bagel+Fat+One"},
    "stylish": {"label": "스타일리시", "group": "구글 · 제목용", "css": "'Stylish', sans-serif", "google": "Stylish"},
    "yeon-sung": {"label": "연성", "group": "구글 · 제목용", "css": "'Yeon Sung', sans-serif", "google": "Yeon+Sung"},
    "dongle": {"label": "동글", "group": "구글 · 제목용", "css": "'Dongle', sans-serif", "google": "Dongle:wght@400;700"},
    "moirai-one": {"label": "Moirai One", "group": "구글 · 제목용", "css": "'Moirai One', sans-serif", "google": "Moirai+One"},
    "black-and-white": {"label": "흑백사진 (Black And White Picture)", "group": "구글 · 제목용", "css": "'Black And White Picture', sans-serif", "google": "Black+And+White+Picture"},
    "nanum-pen": {"label": "나눔손글씨 펜", "group": "구글 · 손글씨", "css": "'Nanum Pen Script', cursive", "google": "Nanum+Pen+Script"},
    "nanum-brush": {"label": "나눔손글씨 붓", "group": "구글 · 손글씨", "css": "'Nanum Brush Script', cursive", "google": "Nanum+Brush+Script"},
    "gaegu": {"label": "개구", "group": "구글 · 손글씨", "css": "'Gaegu', cursive", "google": "Gaegu:wght@400;700"},
    "gamja-flower": {"label": "감자꽃", "group": "구글 · 손글씨", "css": "'Gamja Flower', cursive", "google": "Gamja+Flower"},
    "hi-melody": {"label": "하이멜로디", "group": "구글 · 손글씨", "css": "'Hi Melody', cursive", "google": "Hi+Melody"},
    "poor-story": {"label": "푸어스토리", "group": "구글 · 손글씨", "css": "'Poor Story', cursive", "google": "Poor+Story"},
    "cute-font": {"label": "귀여운 글꼴 (Cute Font)", "group": "구글 · 손글씨", "css": "'Cute Font', cursive", "google": "Cute+Font"},
    "single-day": {"label": "싱글데이", "group": "구글 · 손글씨", "css": "'Single Day', cursive", "google": "Single+Day"},
    "kirang-haerang": {"label": "기랑해랑", "group": "구글 · 손글씨", "css": "'Kirang Haerang', cursive", "google": "Kirang+Haerang"},
    "dokdo": {"label": "독도", "group": "구글 · 손글씨", "css": "'Dokdo', cursive", "google": "Dokdo"},
    "east-sea-dokdo": {"label": "동해독도", "group": "구글 · 손글씨", "css": "'East Sea Dokdo', cursive", "google": "East+Sea+Dokdo"},
}

# 눈누(noonnu.cc)에서 영상 사용 "사용 가능"으로 표시된 폰트 (2026-11-14 수집). key, 이름, family, 묶음, generic, url
G, M, T, H = "눈누 · 고딕", "눈누 · 명조", "눈누 · 제목용", "눈누 · 손글씨"
B = "https://cdn.jsdelivr.net/gh/"
NOONNU = [
    ("nn-pretendard", "프리텐다드", "Pretendard-Regular", G, "sans-serif", B + "projectnoonnu/pretendard@1.0/Pretendard-Regular.woff2"),
    ("nn-paperlogy", "페이퍼로지", "Paperlogy-8ExtraBold", G, "sans-serif", B + "projectnoonnu/2408-3@1.0/Paperlogy-8ExtraBold.woff2"),
    ("nn-gmarket", "G마켓 산스", "GmarketSansMedium", G, "sans-serif", B + "projectnoonnu/noonfonts_2001@1.1/GmarketSansMedium.woff"),
    ("nn-scdream", "에스코어드림", "S-CoreDream-3Light", G, "sans-serif", B + "projectnoonnu/noonfonts_six@1.2/S-CoreDream-3Light.woff"),
    ("nn-bithumb", "빗썸고딕 Original", "Bithumb Gothic Original", G, "sans-serif", B + "Project-Noonnu/2610082345@original/original/Bithumb Gothic Original.woff2"),
    ("nn-freesentation", "프리젠테이션", "Freesentation-9Black", G, "sans-serif", B + "projectnoonnu/2404@1.0/Freesentation-9Black.woff2"),
    ("nn-suit", "수트", "SUIT-Regular", G, "sans-serif", B + "projectnoonnu/noonfonts_suit@1.0/SUIT-Regular.woff2"),
    ("nn-kopub-dotum", "KoPub돋움", "KoPubDotumMedium", G, "sans-serif", B + "projectnoonnu/noonfonts_two@1.0/KoPubDotumMedium.woff"),
    ("nn-chosun-gulim", "조선굴림체", "ChosunGu", G, "sans-serif", B + "projectnoonnu/noonfonts_20-04@1.0/ChosunGu.woff"),
    ("nn-gong-gothic", "이사만루", "GongGothicMedium", G, "sans-serif", B + "projectnoonnu/noonfonts_20-10@1.0/GongGothicMedium.woff"),
    ("nn-a2z", "에이투지체", "에이투지체-7Bold", G, "sans-serif", B + "projectnoonnu/2601-6@1.0/에이투지체-7Bold.woff2"),
    ("nn-nanum-square-round", "나눔스퀘어라운드", "NanumSquareRound", G, "sans-serif", B + "projectnoonnu/noonfonts_two@1.0/NanumSquareRound.woff"),
    ("nn-busan-gothic", "부산단디고딕", "부산단디고딕M", G, "sans-serif", B + "Project-Noonnu/2610132210@l/l/부산단디고딕M.woff2"),
    ("nn-ria", "리아체", "RiaSans-ExtraBold", G, "sans-serif", B + "projectnoonnu/2410-1@1.0/RiaSans-ExtraBold.woff2"),
    ("nn-jalnan-gothic", "여기어때 잘난체 고딕", "JalnanGothic", G, "sans-serif", B + "projectnoonnu/noonfonts_231029@1.1/JalnanGothic.woff"),
    ("nn-bookk-myungjo", "부크크 명조", "BookkMyungjo-Bd", M, "serif", B + "projectnoonnu/noonfonts_2302@1.0/BookkMyungjo-Bd.woff2"),
    ("nn-chosun-gungseo", "조선궁서체", "ChosunGs", M, "serif", B + "projectnoonnu/noonfonts_20-04@1.0/ChosunGs.woff"),
    ("nn-busan-myungjo", "부산단디명조", "부산단디명조M", M, "serif", B + "Project-Noonnu/2610132210@l-2/l/부산단디명조M.woff2"),
    ("nn-chosunilbo", "조선일보명조체", "Chosunilbo_myungjo", M, "serif", B + "projectnoonnu/noonfonts_one@1.0/Chosunilbo_myungjo.woff"),
    ("nn-ridibatang", "리디바탕", "RIDIBatang", M, "serif", B + "projectnoonnu/noonfonts_twelve@1.0/RIDIBatang.woff"),
    ("nn-kopub-batang", "KoPub바탕", "KoPub Batang", M, "serif", B + "Project-Noonnu/2611021659@webfont-32/webfont-32/KoPubBatang-Regular.woff2"),
    ("nn-eulyoo", "을유1945", "Eulyoo1945-Regular", M, "serif", B + "projectnoonnu/noonfonts_2102-01@1.0/Eulyoo1945-Regular.woff"),
    ("nn-jalnan", "여기어때 잘난체", "yg-jalnan", T, "sans-serif", B + "projectnoonnu/noonfonts_four@1.2/JalnanOTF00.woff"),
    ("nn-gs-hyejarown", "GS혜자로운체", "GSHYEJAROUNTTF-Bold", T, "sans-serif", B + "Project-Noonnu/2610102356@gs/gs/GSHYEJAROUNTTF-Bold.woff2"),
    ("nn-aggro", "어그로체", "SBAggroB", T, "sans-serif", B + "projectnoonnu/noonfonts_2108@1.1/SBAggroB.woff"),
    ("nn-ddeoksang", "떡상체", "떡상체", T, "sans-serif", B + "Project-Noonnu/2610132210@font-344/font-344/떡상체.woff2"),
    ("nn-cafe24-ssurround", "카페24 써라운드", "Cafe24Ssurround", T, "sans-serif", B + "projectnoonnu/noonfonts_2105_2@1.0/Cafe24Ssurround.woff"),
    ("nn-levelup", "레벨업", "LevelUp-SemiBold", T, "sans-serif", B + "Project-Noonnu/2610132210@levelup-regular/levelup-regular/LevelUp-SemiBold.woff2"),
    ("nn-kkakdugi", "깍두기 도면체", "KkakdugiDrafting-Light", T, "sans-serif", B + "Project-Noonnu/2611121616@kkakdugidrafting-extralight/kkakdugidrafting-extralight/KkakdugiDrafting-Light.woff2"),
    ("nn-maplestory", "넥슨 메이플스토리", "MaplestoryOTFBold", T, "sans-serif", B + "projectnoonnu/noonfonts_20-04@2.1/MaplestoryOTFBold.woff"),
    ("nn-dancing-peoples", "춤추는사람들", "DancingPeoples-Dance-VF", T, "sans-serif", B + "Project-Noonnu/2610082345@dancingpeoples-dance-vf/dancingpeoples-dance-vf/DancingPeoples-Dance-VF.woff2"),
    ("nn-kkubulim", "꾸불림체", "BMkkubulimTTF-Regular", T, "sans-serif", B + "projectnoonnu/2410-1@1.0/BMkkubulimTTF-Regular.woff2"),
    ("nn-hakgyoansim", "학교안심 둥근미소", "HakgyoansimDunggeunmisoTTF-B", T, "sans-serif", B + "projectnoonnu/2408-5@1.0/HakgyoansimDunggeunmisoTTF-B.woff2"),
    ("nn-onestore-pop", "원스토어 모바일POP체", "ONE-Mobile-POP", T, "sans-serif", B + "projectnoonnu/noonfonts_2105_2@1.0/ONE-Mobile-POP.woff"),
    ("nn-gangwon-edu", "강원교육모두체", "GangwonEdu_OTFBoldA", T, "sans-serif", B + "projectnoonnu/noonfonts_2201-2@1.0/GangwonEdu_OTFBoldA.woff"),
    ("nn-wildgag", "와일드각", "KIMWILDgag-Bold", T, "sans-serif", B + "projectnoonnu/2510-1@1.0/KIMWILDgag-Bold.woff2"),
    ("nn-neujoh", "느좋체", "느좋체R", T, "sans-serif", B + "Project-Noonnu/2610081905@r/r/느좋체R.woff2"),
    ("nn-memoment", "메모먼트 꾹꾹체", "memomentKkukKkuk", H, "cursive", B + "projectnoonnu/2508-2@1.0/memomentKkukKkuk.woff2"),
    ("nn-parkdahyun", "온글잎 박다현체", "Ownglyph_ParkDaHyun", H, "cursive", B + "projectnoonnu/2411-3@1.0/Ownglyph_ParkDaHyun.woff2"),
    ("nn-leeseoyun", "이서윤체", "LeeSeoyun", H, "cursive", B + "projectnoonnu/noonfonts_2202-2@1.0/LeeSeoyun.woff"),
    ("nn-tuktak-potato", "뚝딱감자체", "tuktakpotato", H, "cursive", B + "Project-Noonnu/2610081905@tuktakpotato/tuktakpotato/tuktakpotato.woff2"),
    ("nn-busan-hand", "부산단디손글씨", "부산단디손글씨", H, "cursive", B + "Project-Noonnu/2610132210@font-342/font-342/부산단디손글씨.woff2"),
    ("nn-chai", "차이 활짝체", "ChaiHwaljjak-Medium", H, "cursive", B + "Project-Noonnu/2610082345@chaihwaljjak-regular/chaihwaljjak-regular/ChaiHwaljjak-Medium.woff2"),
    ("nn-corncorn", "온글잎 콘콘체", "Ownglyph_corncorn-Rg", H, "cursive", B + "projectnoonnu/2412-1@1.0/Ownglyph_corncorn-Rg.woff2"),
]

# 눈누 폰트는 파일 주소(url)로 바로 불러온다. 영상 사용 가능 여부는 수집 당시 눈누 표기 기준이며,
# 출처 표기 등 세부 조건은 폰트마다 다르니 눈누 페이지에서 확인할 것.
for _key, _label, _family, _group, _generic, _url in NOONNU:
    FONTS[_key] = {"label": _label, "group": _group, "css": f"'{_family}', {_generic}", "google": None, "url": _url}


SUBTITLE_SIZE_RANGE = (36, 96)
TITLE_SIZE_RANGE = (48, 140)
# remotion/src/layout.ts의 안전 영역, 텍스트 패딩과 같은 값이다.
SUBTITLE_TEXT_WIDTH = 680
SUBTITLE_BOTTOM_RANGE = (696, 796)


def defaults() -> dict:
    return {
        "subtitle_font": "",  # 빈 값 = .env의 SUBTITLE_FONT
        "subtitle_size": settings.subtitle_size,
        "subtitle_color": settings.subtitle_color,
        "subtitle_bottom": SUBTITLE_BOTTOM_RANGE[0],  # 화면 아래에서 자막 아랫변까지(px)
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
    lo, hi = SUBTITLE_BOTTOM_RANGE
    style["subtitle_bottom"] = max(lo, min(hi, int(style["subtitle_bottom"])))
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
    lo, hi = SUBTITLE_BOTTOM_RANGE
    merged["subtitle_bottom"] = max(lo, min(hi, int(merged["subtitle_bottom"])))
    merged["title_show"] = bool(merged["title_show"])
    for key in ("subtitle_color", "title_color"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(merged[key])):
            raise ValueError(f"색상은 #RRGGBB 형식이어야 합니다: {merged[key]}")
        merged[key] = merged[key].lower()
    (job_dir / STYLE_FILE).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def font_css(key: str, fallback: str) -> str:
    return FONTS[key]["css"] if key in FONTS else fallback


def font_url(key: str) -> str:
    """눈누 폰트 파일 주소 (빈 값이면 해당 없음)"""
    return (FONTS.get(key) or {}).get("url") or ""


def google_spec(key: str) -> str:
    """Remotion이 렌더 전에 불러올 구글 폰트 (빈 값이면 PC 글꼴)"""
    return (FONTS.get(key) or {}).get("google") or ""


def line_chars(subtitle_size: int) -> int:
    """안전 영역 안에서 자막 패딩을 제외한 폭 기준으로 한 줄 글자 수를 추정한다."""
    return max(1, SUBTITLE_TEXT_WIDTH // subtitle_size)


def remotion_style(st: dict) -> dict:
    """s08이 Remotion props.style로 넘기는 값"""
    sub_font = font_css(st["subtitle_font"], settings.subtitle_font)
    title_key = st["title_font"] or st["subtitle_font"]
    title_font = font_css(title_key, settings.title_font or sub_font)
    return {
        "subtitle": {
            "font": sub_font,
            "size": st["subtitle_size"],
            "weight": settings.subtitle_weight,
            "color": st["subtitle_color"],
            "bottom": st["subtitle_bottom"],
            "google": google_spec(st["subtitle_font"]),
            "url": font_url(st["subtitle_font"]),
        },
        "title": {
            "font": title_font,
            "size": st["title_size"],
            "color": st["title_color"],
            "google": google_spec(title_key),
            "url": font_url(title_key),
        },
    }
