"""TTS 직전 발음 변환.

GPT가 쓴 내레이션에 남은 숫자·영문·기호를 정해진 규칙으로 '읽는 그대로의 한글'로 바꾼다.
자막(subtitle_text)에는 원래 표기가 그대로 남는다.

적용 순서 (앞 단계에서 한글로 바뀐 부분은 뒤 단계가 다시 건드리지 않는다)
   1) 사전          TOEIC → 토익, Q&A → 큐앤에이, Bow-tie → 보우타이, CAD → 캐드
   2) 특수 표기     D-30 → 디데이 삼십, No.1 → 넘버원, 1st → 첫 번째, x2 → 두 배
   3) 전화번호      1588-1234 → 일오팔팔에 일이삼사, 02-123-4567 → 공이에 일이삼에 사오육칠
   4) 날짜·분수     2026.11.14(금) → 이천이십육 년 십일 월 십사 일 금요일, '26년 → 이십육 년, 1/3 → 삼분의 일
   5) 시각·비율     15:30 → 열다섯 시 삼십 분, 30:1 → 삼십 대 일
   6) 화폐          $100 → 백 달러, ₩5,000 → 오천 원
   7) 범위(~)       1일~16일 → 일 일부터 십육 일까지, 3~4주 → 삼사 주, 2~3개 → 두세 개,
                    2~30 → 이삼십, 70~80% → 칠십에서 팔십 퍼센트
   8) 숫자+단위     5km → 오 킬로미터, -5℃ → 영하 오 도, 2달 → 두 달, 15시 → 열다섯 시, 10월 → 시월,
                    60문제 → 육십 문제, 3번 문제 → 삼 번 문제, 3번 응시 → 세 번 응시
   9) 남은 숫자     1,000 → 천, 64.0 → 육십사, 09 → 구, 1만 2천 → 만 이천, 1억 → 일억
  10) 영문          5G → 파이브지, A4 → 에이포, CBT → 씨비티, A형 → 에이형 (그 밖의 영어 단어는 그대로)
  11) 기호          Ⅱ → 이, → ※ ★ 같은 장식 기호는 지움
  12) 공백 정리

숫자와 단위 사이는 띄운다 (두 달, 오 킬로미터). 단위가 아닌 조사는 붙인다 (1과 2 → 일과 이).
GPT가 이미 한글로 쓴 표현(스무 문제, 십월 등)은 숫자가 아니므로 건드리지 않는다.

자막 싱크 보호: s07은 자막 문장과 읽는 문장에서 '뒤에 공백이 오는(또는 문장 끝의) 쉼표·마침표·물음표·느낌표'
개수가 같아야 정밀 싱크를 쓴다. 그래서 변환 전후로 이 개수가 바뀌면 안 된다.
  - 띄어 쓴 날짜(2026. 11. 14.)는 점을 남긴 채 읽는다 → 이천이십육 년. 십일 월. 십사 일.
  - 문장부호 바로 뒤에 붙은 장식 기호(합니다.★ 다음)는 지우면 개수가 늘어나므로 남긴다
  - 그래도 개수가 달라지면 경고를 남긴다

애매해서 바꾸지 않은 곳(뜻을 알 수 없는 '3번' 등)과 판단이 필요한 곳은 analyze()의 notes로 확인한다.
"""
import re
from dataclasses import dataclass, field

from .logger import log

# ---------------------------------------------------------------- 사전
# 단어처럼 읽는 약어·고유명사. 대소문자를 구분하고, 앞뒤가 영문·숫자가 아닐 때만 바꾼다.
PRONUNCIATIONS = {
    # 시험·자격증
    "TOEIC": "토익", "TOEFL": "토플", "TEPS": "텝스", "OPIc": "오픽", "OPIC": "오픽", "TOPIK": "토픽",
    "PSAT": "피셋", "LEET": "리트", "GSAT": "지에스에이티", "MOS": "모스", "ADsP": "에이디에스피",
    "NCLEX": "엔클렉스", "UWorld": "유월드", "Q-net": "큐넷", "Q-Net": "큐넷",
    "333 위아너스": "삼삼삼 위아너스",  # 숫자를 하나씩 읽는 교재 이름
    # 기업·기관
    "POSCO": "포스코", "KOTRA": "코트라", "KOSHA": "코샤",
    # 일반
    "CAD": "캐드", "COVID-19": "코로나 일구", "COVID": "코로나", "IoT": "아이오티",
    "Q&A": "큐앤에이", "R&D": "알앤디", "Bow-tie": "보우타이", "Trend": "트렌드",
}

LETTERS = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}
# 영문과 붙은 숫자는 영어로 읽는다 (5G 파이브지, A4 에이포). 10보다 크면 한자어 (G20 지이십)
ENGLISH_NUM = ["제로", "원", "투", "쓰리", "포", "파이브", "식스", "세븐", "에잇", "나인", "텐"]

DIGITS = "영일이삼사오육칠팔구"
PHONE_DIGITS = "공일이삼사오육칠팔구"  # 전화번호의 0은 '공'

# ---------------------------------------------------------------- 단위
# 고유어로 읽는 단위와 고유어로 읽는 최대 수. 넘으면 한자어 (60문제 → 육십 문제)
NATIVE_UNITS = {
    "번째": 99, "살": 99, "시": 24,
    "시간": 20, "달": 20, "배": 20, "개": 20, "명": 20, "마리": 20, "권": 20, "장": 20,
    "가지": 20, "군데": 20, "문제": 20,
}
# 한자어로 읽는 단위 (숫자 뒤에 띄어 읽는다)
SINO_UNITS = [
    "분", "초", "월", "일", "년", "주", "개월", "원", "점", "회", "급", "층", "학점", "세", "위", "차",
    "퍼센트", "개년", "개국", "회차", "회독", "주차", "주년", "일차", "분기", "교시", "학년", "학기", "년도",
    "문항", "과목", "단계", "등", "호", "쪽", "페이지", "달러",
]
# 범위에서 '부터 ~까지'로 읽는 날짜·시각 단위
TIME_UNITS = {"년", "월", "일", "시", "분", "초", "주차", "회차", "교시", "일차"}
# 단위 글자로 시작하는 다른 낱말을 단위로 오인하지 않도록 (3시행 X, 2장점 X)
_UNIT_GUARD = {
    "시": "간|행|험|청|장|대|기|작|점|민|설|각", "장": "점|학|기|애|르|비|소|면", "일": "정|반",
    "주": "요|식", "점": "검|심", "원": "서|인|리", "세": "계|금|부|요", "위": "해|원|치|험",
    "차": "이|량", "등": "록|장", "배": "우|송|치|포|정", "명": "단|칭|함|령|소", "권": "한|장|리|유",
    "급": "여|식|증", "회": "사|원|장|계|식", "초": "급|등|과|반|보", "분": "석|야|류|량|할|들|께",
}

# 단위 기호 (숫자 바로 뒤, 공백 하나 허용). 여러 글자짜리는 대소문자 무시 (5KM → 오 킬로미터)
_SYM_UNITS = [
    (r"(?i:kwh)", "킬로와트시"), (r"(?i:kw)", "킬로와트"), (r"(?i:km)|㎞", "킬로미터"),
    (r"(?i:kg)|㎏", "킬로그램"), (r"(?i:cm)|㎝", "센티미터"), (r"(?i:mm)|㎜", "밀리미터"),
    (r"(?i:ml)|㎖", "밀리리터"), (r"㎡|m²", "제곱미터"), (r"㎥|m³", "세제곱미터"),
    (r"(?i:gb)", "기가바이트"), (r"(?i:mb)", "메가바이트"), (r"(?i:tb)", "테라바이트"),
    (r"(?i:hz)", "헤르츠"), (r"℃|°C", "도"), (r"%[pP]", "퍼센트포인트"), (r"%", "퍼센트"),
    (r"m", "미터"), (r"g", "그램"), (r"t", "톤"), (r"[Llℓ]", "리터"),
    (r"V", "볼트"), (r"A", "암페어"), (r"W", "와트"),
]

# '번'은 뒤에 오는 말로 판단한다. 한자어 목록을 먼저 보고, 긴 낱말부터 맞춘다 ('보기'가 '보'보다 먼저)
_BEON_SINO = sorted(["문제", "문항", "항목", "출구", "선", "버스", "트랙", "지문", "보기"], key=len, reverse=True)
_BEON_NATIVE = sorted(["이상", "정도", "만에", "씩", "더", "응시", "도전", "반복", "시험",
                       "읽", "풀", "보", "써", "했", "해"], key=len, reverse=True)

_NATIVE_PAIR = {1: "한두", 2: "두세", 3: "서너", 4: "네다섯", 5: "대여섯", 6: "예닐곱", 7: "일고여덟", 8: "여덟아홉"}
_SINO_PAIR = {1: "일이", 2: "이삼", 3: "삼사", 4: "사오", 5: "오륙", 6: "육칠", 7: "칠팔", 8: "팔구"}
_ROMAN = {c: i for i, c in enumerate("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ", 1)} | {c: i for i, c in enumerate("ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻ", 1)}
_WEEKDAY = "월화수목금토일"


# ---------------------------------------------------------------- 숫자 읽기
def read_number(n: str) -> str:
    """한자어 숫자: 2005 → 이천오, 1,000 → 천, 09 → 구, 3.5 → 삼 점 오, 64.0 → 육십사"""
    n = n.replace(",", "")
    if "." in n:
        whole, frac = n.split(".", 1)
        frac = frac.rstrip("0")
        head = read_number(whole or "0")
        return head + (" 점 " + "".join(DIGITS[int(d)] for d in frac) if frac else "")
    num = int(n)
    if num == 0:
        return "영"
    units = ["", "십", "백", "천"]
    big = ["", "만", "억", "조", "경"]
    groups, group = [], 0
    while num > 0:
        chunk, num = num % 10000, num // 10000
        part = ""
        for pos in range(3, -1, -1):
            d = (chunk // 10 ** pos) % 10
            if d:
                part += ("" if d == 1 and pos > 0 else DIGITS[d]) + units[pos]
        if part:
            if group == 1 and part == "일":
                part = ""  # 10000 → 만 (일만 X). 1억은 '일억'으로 읽는다
            groups.insert(0, part + big[group])
        group += 1
    return " ".join(groups)  # 15000 → 만 오천 (만·억 단위 사이는 띄운다)


_ONES_MOD = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]
_ONES_CARD = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉"]
_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]


def read_native(n: int, cardinal: bool = False) -> str:
    """고유어 숫자 (1~99). 꾸밈 형태: 한·두·세·스무·스물한 / cardinal=True: 하나·둘·셋·스물"""
    if n == 0:
        return "영"
    tens, ones = divmod(n, 10)
    if n == 20 and not cardinal:
        return "스무"
    return _TENS[tens] + (_ONES_CARD if cardinal else _ONES_MOD)[ones]


_PLAIN = r"\d+(?:,\d{3})*(?:\.\d+)?"
_BIG_SUFFIX = r"(?:[천백]?[조억만]|[천백])"
_NUM = rf"(?:{_PLAIN}{_BIG_SUFFIX}(?:\s?{_PLAIN}{_BIG_SUFFIX})*|{_PLAIN})"  # 1만 2천, 3억 5천만, 1,000, 3.5
_BIG_PIECE = re.compile(rf"({_PLAIN})({_BIG_SUFFIX})")


def read_numexpr(s: str) -> str:
    """숫자 + 만·억 묶음: 1만 2천 → 만 이천, 30만 → 삼십만, 1천만 → 천만, 1억 → 일억"""
    pieces = _BIG_PIECE.findall(s)
    if not pieces:
        return read_number(s)
    out = []
    for num, suffix in pieces:
        r = read_number(num)
        if r == "일" and suffix[0] in "만천백":
            r = ""
        out.append(r + suffix)
    return " ".join(out)


def _int(num: str):
    """정수로 읽을 수 있으면 int (64.0 포함), 아니면 None (소수·만억 묶음)"""
    s = num.replace(",", "")
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\d+\.0+", s):
        return int(s.split(".")[0])
    return None


def _month(m: int) -> str:
    return {6: "유월", 10: "시월"}.get(m, f"{read_number(str(m))} 월")


def _english_or_sino(n: str) -> str:
    return ENGLISH_NUM[int(n)] if int(n) <= 10 else read_number(n)


# ---------------------------------------------------------------- 정규식
def _alt(units) -> str:
    return "|".join(u + (f"(?!{_UNIT_GUARD[u]})" if u in _UNIT_GUARD else "")
                    for u in sorted(units, key=len, reverse=True))


_KOR_ALT = _alt(set(NATIVE_UNITS) | set(SINO_UNITS))
_SYM_ALT = "|".join(f"(?:{p})" for p, _ in _SYM_UNITS)
_NB = r"(?<![A-Za-z\d])"  # 앞이 영문·숫자가 아님 (A4, B2B 속 숫자 제외)

_DICT_RE = re.compile(_NB + "(" + "|".join(re.escape(k) for k in sorted(PRONUNCIATIONS, key=len, reverse=True))
                      + r")(?![A-Za-z\d])")
_DDAY = re.compile(r"(?<![A-Za-z])D-(?:[Dd]ay|DAY)(?![A-Za-z])")
_DNUM = re.compile(r"(?<![A-Za-z])D([-+])(\d+)(?!\d)")
_NO = re.compile(r"(?<![A-Za-z])No\.(\d+)(?!\d)")
_NO_SPACED = re.compile(r"(?<![A-Za-z])No\.\s+\d+")
_ORDINAL = re.compile(_NB + r"(\d+)(?i:st|nd|rd|th)(?![A-Za-z])")
_TIMES = re.compile(_NB + r"[x×](\d+)(?![\d.A-Za-z])")
_PHONE = re.compile(r"(?<![\d-])(0\d{1,2}-\d{3,4}-\d{4}|1[5-9]\d{2}-\d{4})(?![\d-])")
_WD = rf"(?:\s?\(([{_WEEKDAY}])(?:요일)?\))?"
_DATE_YMD = re.compile(r"(?<![\d.])((?:19|20)\d{2})([.\-/])(\d{1,2})\2(\d{1,2})(?!\d)" + _WD)
_DATE_SPACED = re.compile(r"(?<![\d.])((?:19|20)\d{2})\.(\s+)(\d{1,2})\.(\s+)(\d{1,2})(?!\d)")
_YY = re.compile(r"['’‘](\d{2})\s?년")
_MD = re.compile(r"(?<![\d./])(\d{1,2})/(\d{1,2})(?![\d/])" + _WD)
_SLASH = re.compile(r"(?<![\d./])(\d+)/(\d+)(?![\d/])")
_FRAC_WORD = re.compile(_NB + r"(\d+)분의\s?(\d+)(?!\d)")
_DAY_WD = re.compile(rf"(?<=\d일)\s?\(([{_WEEKDAY}])(?:요일)?\)")
_T = r"\d{1,2}:\d{2}"
_TIME_RANGE = re.compile(rf"(?<![\d:])({_T})\s*[~∼〜]\s*({_T})(?![\d:])")
_COLON = re.compile(r"(?<![\d:])(\d+)(\s*):(\s*)(\d+)(?![\d:])")
_RATIO_CONTEXT = re.compile(r"(경쟁률|비율|배율|대비)\s*(은|는|이|가)?\s*$")
_DOLLAR = re.compile(rf"[$＄]\s?({_NUM})")
_WON = re.compile(rf"[₩￦]\s?({_NUM})")
_COMPOUND = r"\d{1,2}월\s?\d{1,2}일|\d{1,2}시\s?\d{1,2}분"
_COMPOUND_RANGE = re.compile(_NB + rf"({_COMPOUND})\s*[~∼〜]\s*({_COMPOUND}|\d{{1,2}}(?:일|시|분))(?!\d)")


def _term_re(i: int) -> str:
    return rf"(?P<n{i}>{_NUM})(?:(?P<k{i}>{_KOR_ALT})|(?P<p{i}>\s?)(?P<s{i}>{_SYM_ALT})(?![A-Za-z²³]))?"


_RANGE = re.compile(_NB + _term_re(1) + r"\s*[~∼〜]\s*" + _term_re(2) + r"(?!\d)")
_SYM_TERM = re.compile(rf"(?:(?<![\w.])(?P<neg>[-−+]))?{_NB}(?P<n>{_NUM})(?P<p>\s?)(?P<s>{_SYM_ALT})(?![A-Za-z²³])")
_KOR_TERM = re.compile(rf"{_NB}(?P<n>{_NUM})(?P<k>{_KOR_ALT})")
_BEON = re.compile(_NB + r"(\d+)번(?!째)")
_PLAIN_NUM = re.compile(rf"{_NB}({_NUM})(?![\dA-Za-z])")
_ALNUM = re.compile(r"(?<![A-Za-z\d])(?=[A-Za-z\d]*\d)(?=[A-Za-z\d]*[A-Za-z])[A-Za-z\d]+(?![A-Za-z\d])")
_AMP = re.compile(r"(?<![A-Za-z])([A-Z]+(?:&[A-Z]+)+)(?![A-Za-z])")
_UPPER = re.compile(r"(?<![A-Za-z])[A-Z]{1,6}(?![A-Za-z])")
_DECOR = re.compile("[←-⇿─-◿☀-➿⬀-⯿※•‣"
                    "\U0001F000-\U0001FAFF️]+")
_PHRASE_END = re.compile(r"[.?!,](?=\s|$)")  # s07_subtitle과 같은 기준
_SENTENCE_END = re.compile(r"[.?!](?=\s|$)")


def _sym_name(sym: str) -> str:
    return next(name for p, name in _SYM_UNITS if re.fullmatch(p, sym))


def _kor_term(num: str, unit: str, je: bool = False) -> str:
    """숫자 + 한글 단위. je=True면 '제3장'처럼 순서를 뜻하므로 한자어"""
    if unit == "월" and _int(num) in (6, 10):
        return _month(_int(num))
    v = _int(num)
    if unit in NATIVE_UNITS and not je and v is not None and 1 <= v <= NATIVE_UNITS[unit]:
        if unit == "번째" and v == 1:
            return "첫 번째"
        return f"{read_native(v)} {unit}"
    return f"{read_numexpr(num)} {unit}"


def _sym_term(num: str, sym: str) -> str:
    return f"{read_numexpr(num)} {_sym_name(sym)}"


def _punct_counts(text: str) -> tuple[int, int]:
    return len(_PHRASE_END.findall(text)), len(_SENTENCE_END.findall(text))


# ---------------------------------------------------------------- 변환
@dataclass
class Result:
    speech: str
    notes: list[tuple[str, str]] = field(default_factory=list)  # (종류, 원문 조각)


def analyze(text: str) -> Result:
    notes: list[tuple[str, str]] = []
    kept: list[str] = []

    def keep(s: str) -> str:
        """바꾸지 않을 조각을 자리표시 문자로 감춰 뒤 단계가 건드리지 못하게 한다"""
        kept.append(s)
        return chr(0xE000 + len(kept) - 1)

    # 1) 사전
    text = _DICT_RE.sub(lambda m: PRONUNCIATIONS[m.group(1)], text)

    # 2) 특수 표기
    text = _DDAY.sub("디데이", text)
    text = _DNUM.sub(lambda m: ("디데이 " if m.group(1) == "-" else "디플러스 ") + read_number(m.group(2)), text)
    text = _NO.sub(lambda m: "넘버" + _english_or_sino(m.group(1)), text)

    def no_spaced(m):  # 'No. 1'의 점은 뒤에 공백이 있어 자막 싱크 기준 문장부호 → 그대로 둔다
        notes.append(("바꾸지 않음(No. 띄어씀)", m.group(0)))
        return keep(m.group(0))
    text = _NO_SPACED.sub(no_spaced, text)

    def ordinal(m):
        v = int(m.group(1))
        return "첫 번째" if v == 1 else (f"{read_native(v)} 번째" if v <= 99 else f"{read_number(m.group(1))} 번째")
    text = _ORDINAL.sub(ordinal, text)
    text = _TIMES.sub(lambda m: _kor_term(m.group(1), "배"), text)

    # 3) 전화번호
    text = _PHONE.sub(lambda m: "에 ".join("".join(PHONE_DIGITS[int(d)] for d in part)
                                           for part in m.group(1).split("-")), text)

    # 4) 날짜·분수
    def ymd(m):
        y, mo, d, wd = m.group(1), int(m.group(3)), int(m.group(4)), m.group(5)
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return m.group(0)
        return f"{read_number(y)} 년 {_month(mo)} {read_number(str(d))} 일" + (f" {wd}요일" if wd else "")
    text = _DATE_YMD.sub(ymd, text)

    def ymd_spaced(m):  # 점 뒤에 공백 → 자막 싱크 기준 문장부호이므로 점을 남긴다
        y, s1, mo, s2, d = m.groups()
        if not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
            return m.group(0)
        return f"{read_number(y)} 년.{s1}{_month(int(mo))}.{s2}{read_number(d)} 일"
    text = _DATE_SPACED.sub(ymd_spaced, text)
    text = _YY.sub(lambda m: f"{read_number(m.group(1))} 년", text)

    def md(m):
        a, b, wd = int(m.group(1)), int(m.group(2)), m.group(3)
        date = f"{_month(a)} {read_number(str(b))} 일" + (f" {wd}요일" if wd else "")
        if wd and 1 <= a <= 12 and 1 <= b <= 31:
            return date
        if 1 <= a <= 12 and 13 <= b <= 31:
            return date
        if 1 <= b <= 10:
            return f"{read_number(str(b))}분의 {read_number(str(a))}" + (f" ({wd})" if wd else "")
        if 1 <= a <= 12 and 1 <= b <= 31:
            notes.append(("날짜로 읽음(분수일 수도 있음)", m.group(0)))
            return date
        return f"{read_number(str(b))}분의 {read_number(str(a))}"
    text = _MD.sub(md, text)
    text = _SLASH.sub(lambda m: f"{read_number(m.group(2))}분의 {read_number(m.group(1))}", text)
    text = _FRAC_WORD.sub(lambda m: f"{read_number(m.group(1))}분의 {read_number(m.group(2))}", text)
    text = _DAY_WD.sub(lambda m: f" {m.group(1)}요일", text)

    # 5) 시각·비율
    def is_time(h: str, mm: str, before: str) -> bool:
        return (len(mm) == 2 and int(h) <= 24 and int(mm) <= 59
                and not _RATIO_CONTEXT.search(before[-10:]))

    def read_time(t: str) -> str:
        h, mm = (int(x) for x in t.split(":"))
        return (f"{read_native(h)} 시" if h else "영 시") + (f" {read_number(str(mm))} 분" if mm else "")

    def time_range(m):
        a, b = m.group(1), m.group(2)
        if not (is_time(*a.split(":"), m.string[:m.start()]) and is_time(*b.split(":"), "")):
            return m.group(0)
        return f"{read_time(a)}부터 {read_time(b)}까지"
    text = _TIME_RANGE.sub(time_range, text)

    def colon(m):
        h, sp1, sp2, mm = m.groups()
        if not sp1 and not sp2 and is_time(h, mm, m.string[:m.start()]):
            return read_time(f"{h}:{mm}")
        return f"{h} 대 {mm}"  # 비율 (숫자는 9단계에서 읽는다)
    text = _COLON.sub(colon, text)

    # 6) 화폐
    text = _DOLLAR.sub(lambda m: f"{read_numexpr(m.group(1))} 달러", text)
    text = _WON.sub(lambda m: f"{read_numexpr(m.group(1))} 원", text)

    # 7) 범위
    def units_only(s: str) -> str:
        return _KOR_TERM.sub(lambda m: _kor_term(m.group("n"), m.group("k")), s)
    text = _COMPOUND_RANGE.sub(lambda m: f"{units_only(m.group(1))}부터 {units_only(m.group(2))}까지", text)

    def rng(m):
        n1, k1, s1 = m.group("n1"), m.group("k1"), m.group("s1")
        n2, k2, s2, p2 = m.group("n2"), m.group("k2"), m.group("s2"), m.group("p2")
        rest = m.string[m.end():]
        if not (k2 or s2) and rest[:1].isalpha() and rest[:1].isascii():
            return m.group(0)  # 3~5G 같은 영문 조합은 범위로 보지 않음

        def right() -> str:
            return _kor_term(n2, k2) if k2 else (_sym_term(n2, s2) if s2 else read_numexpr(n2))
        tail = f" {k2}" if k2 else (f" {_sym_name(s2)}" if s2 else "")
        # 줄여 쓴 범위: 2~30 → 이삼십, 4~50만 → 사오십만
        if not (k1 or s1) and re.fullmatch(r"\d", n1):
            mm = re.fullmatch(rf"(\d+)({_BIG_SUFFIX})?", n2)
            if mm:
                head = mm.group(1).rstrip("0")
                if len(mm.group(1)) > len(head) and len(head) == 1 and int(head) == int(n1) + 1:
                    return DIGITS[int(n1)] + read_number(mm.group(1)) + (mm.group(2) or "") + tail
        a, b = _int(n1), _int(n2)
        # 이어지는 작은 수: 3~4주 → 삼사 주, 2~3개 → 두세 개
        if not (k1 or s1) and a and b and 1 <= a <= 8 and b == a + 1:
            if k2 in NATIVE_UNITS and k2 != "번째" and b <= NATIVE_UNITS[k2]:
                return f"{_NATIVE_PAIR[a]} {k2}"
            return _SINO_PAIR[a] + tail
        # 날짜·시각 단위: 1일~16일 → 일 일부터 십육 일까지 (왼쪽에 단위가 없으면 오른쪽 단위로 읽음)
        if k2 in TIME_UNITS and (k1 in TIME_UNITS or not (k1 or s1)):
            return f"{_kor_term(n1, k1 or k2)}부터 {right()}까지"
        # 그 밖: '에서' (3~5개 → 셋에서 다섯 개, 70~80% → 칠십에서 팔십 퍼센트)
        if k1:
            left = _kor_term(n1, k1)
        elif s1:
            left = _sym_term(n1, s1)
        elif k2 in NATIVE_UNITS and a and 1 <= a <= NATIVE_UNITS[k2] and k2 != "번째":
            left = read_native(a, cardinal=True)
        else:
            left = read_numexpr(n1)
        return f"{left}에서 {right()}"
    text = _RANGE.sub(rng, text)

    # 8) 숫자 + 단위
    def sym(m):
        n, p, s, neg = m.group("n"), m.group("p"), m.group("s"), m.group("neg")
        nxt = m.string[m.end():m.end() + 1]
        if p and len(s) == 1 and s.isascii() and re.match(r"[가-힣]", nxt):
            return m.group(0)  # '3 A형'처럼 띄어 쓴 한 글자 뒤에 한글 → 단위 아님
        name = _sym_name(s)
        if neg == "+":
            return "플러스 " + _sym_term(n, s)
        if neg:
            return ("영하 " if name == "도" else "마이너스 ") + _sym_term(n, s)
        return _sym_term(n, s)
    text = _SYM_TERM.sub(sym, text)
    text = _KOR_TERM.sub(lambda m: _kor_term(m.group("n"), m.group("k"),
                                             je=m.start() > 0 and m.string[m.start() - 1] == "제"), text)

    def beon(m):
        after = m.string[m.end():]
        after = after[1:] if after[:1] == " " else after
        je = m.start() > 0 and m.string[m.start() - 1] == "제"
        if je or any(after.startswith(w) for w in _BEON_SINO):
            return f"{read_number(m.group(1))} 번"
        if any(after.startswith(w) for w in _BEON_NATIVE):
            return _kor_term(m.group(1), "번") if int(m.group(1)) > 20 else f"{read_native(int(m.group(1)))} 번"
        notes.append(("바꾸지 않음(번)", m.group(0) + after[:4]))
        return keep(m.group(0))
    text = _BEON.sub(beon, text)

    # 9) 남은 숫자
    text = _PLAIN_NUM.sub(lambda m: read_numexpr(m.group(1)), text)

    # 10) 영문
    def alnum(m):
        return "".join(_english_or_sino(p) if p.isdigit() else "".join(LETTERS[c] for c in p.upper())
                       for p in re.findall(r"[A-Za-z]+|\d+", m.group(0)))
    text = _ALNUM.sub(alnum, text)
    text = _AMP.sub(lambda m: "앤".join("".join(LETTERS[c] for c in part) for part in m.group(1).split("&")), text)
    text = _UPPER.sub(lambda m: "".join(LETTERS[c] for c in m.group(0)), text)

    # 11) 기호
    text = re.sub("[" + "".join(_ROMAN) + "]",
                  lambda m: (" " if m.start() > 0 and not m.string[m.start() - 1].isspace() else "")
                  + read_number(str(_ROMAN[m.group(0)])), text)

    def decor(m):
        prev = m.string[m.start() - 1] if m.start() > 0 else ""
        nxt = m.string[m.end()] if m.end() < len(m.string) else ""
        if prev in ".?!," and prev and (not nxt or nxt.isspace()):
            notes.append(("기호 유지(문장부호 뒤)", prev + m.group(0)))
            return m.group(0)  # 지우면 문장부호 뒤가 공백이 되어 자막 싱크 기준 개수가 늘어난다
        return " "
    text = _DECOR.sub(decor, text)

    # 12) 공백 정리
    text = re.sub(r"(?<=[가-힣])-(?=[가-힣])", " ", text)     # 엔클렉스-알엔 → 엔클렉스 알엔
    text = re.sub(r"(?<=[가-힣])[~∼〜](?=[가-힣])", "에서 ", text)  # 범위로 못 읽은 나머지 (백 달러~이백 달러)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"(?<=[^\s.?!,])[ \t]+(?=[.?!,])", "", text)
    text = text.strip()
    text = re.sub("[-]", lambda m: kept[ord(m.group(0)) - 0xE000], text)
    return Result(text, notes)


def to_speech(text: str) -> str:
    """TTS에 보낼 문장. 자막 싱크 기준 문장부호 개수가 바뀌면 경고를 남긴다."""
    speech = analyze(text).speech
    if _punct_counts(speech) != _punct_counts(text):
        log.warning(f"[pronounce] 문장부호 개수가 바뀜 → 자막 싱크가 문장 단위로 내려갈 수 있음: {text!r} → {speech!r}")
    return speech


if __name__ == "__main__":
    # 전체 예시는 pipeline/tests/test_pronounce.py
    for t in ["필기는 객관식 CBT, 실기는 15~20문항을 150분 동안 풉니다.",
              "2026.11.14(금) 15:30까지 접수하고, 실기는 2달 정도 준비하세요.",
              "합격률은 64.0%로 3%p 올랐고, 경쟁률은 30:1이었습니다.",
              "TOEIC 대신 OPIc을 보고, 3~4주 동안 1~2개씩 풀어 보세요."]:
        r = analyze(t)
        print(t, "\n →", r.speech, ("\n   notes: " + str(r.notes)) if r.notes else "")
