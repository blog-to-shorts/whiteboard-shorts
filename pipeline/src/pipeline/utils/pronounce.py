"""TTS 직전 영문 발음 변환.

GPT에게 영문 약어를 한글로 바꾸게 하면 'CBT → 케이비티'처럼 결과가 들쭉날쭉해서,
정해진 규칙으로 코드가 바꾼다. 자막에는 원래 영문 표기가 그대로 남는다.

  1) 발음 사전에 있는 단어 → 사전 발음        NCLEX → 엔클렉스
  2) 대문자 약어 (2~6자)   → 알파벳 이름       CBT → 씨비티, PAT → 피에이티
  3) 그 밖의 영어 단어      → 그대로 (TTS가 영어로 읽음)  Saunders
  4) 대본에 남은 숫자       → 한자어 숫자      106학점 → 백육학점, 70~80% → 칠십에서 팔십 퍼센트
     (GPT가 이미 '스무 문제'처럼 바꾼 고유어 표현은 건드리지 않는다)
"""
import re

# 단어처럼 읽는 약어·고유명사. 필요하면 여기에 추가한다.
PRONUNCIATIONS = {
    "333": "삼삼삼",  # 333 위아너스 (숫자를 하나씩 읽는 상품명)
    "NCLEX": "엔클렉스",
    "UWorld": "유월드",
    "Q-net": "큐넷",
    "Q-Net": "큐넷",
}

LETTERS = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z\-]*")


def _convert_word(word: str) -> str:
    if word in PRONUNCIATIONS:
        return PRONUNCIATIONS[word]
    # NCLEX-RN처럼 하이픈으로 이어진 경우 조각별로 변환
    if "-" in word:
        return " ".join(_convert_word(part) for part in word.split("-") if part)
    if word.isupper() and 2 <= len(word) <= 6:
        return "".join(LETTERS[ch] for ch in word)
    return word


DIGITS = "영일이삼사오육칠팔구"
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def read_number(n: str) -> str:
    """한자어 숫자 읽기: 2005 → 이천오, 106 → 백육, 3.5 → 삼 점 오"""
    if "." in n:
        whole, frac = n.split(".", 1)
        return read_number(whole) + " 점 " + "".join(DIGITS[int(d)] for d in frac)
    num = int(n)
    if num == 0:
        return "영"
    units = ["", "십", "백", "천"]
    big = ["", "만", "억", "조"]
    out, group = "", 0
    while num > 0:
        chunk, num = num % 10000, num // 10000
        part = ""
        for pos in range(3, -1, -1):
            d = (chunk // 10 ** pos) % 10
            if d:
                part += ("" if d == 1 and pos > 0 else DIGITS[d]) + units[pos]
        if part:
            if group == 1 and part == "일":
                part = ""  # 10000 → 만 (일만 X)
            out = part + big[group] + out
        group += 1
    return out


def _numbers_to_speech(text: str) -> str:
    text = re.sub(r"(\d)\s*~\s*(\d)", r"\1에서 \2", text)   # 70~80 → 70에서 80
    text = _NUMBER.sub(lambda m: read_number(m.group(0)), text)
    return text.replace("%", " 퍼센트")


def to_speech(text: str) -> str:
    # 1) 숫자가 들어간 사전 단어(333 등)를 먼저 바꾼다
    for key, val in PRONUNCIATIONS.items():
        if any(ch.isdigit() for ch in key):
            text = text.replace(key, val)
    # 2) 영문 단어 → 3) 남은 숫자
    text = _WORD.sub(lambda m: _convert_word(m.group(0)), text)
    return _numbers_to_speech(text)


if __name__ == "__main__":
    for t in ["필기는 객관식 CBT예요.", "NCLEX-RN 준비에는 UWorld와 Saunders를 써요.",
              "포스코 PAT는 인적성 검사입니다.", "NGN 신유형과 AI 문제",
              "333 위아너스 NCLEX-RN은 요약형 교재입니다.",
              "응시자격은 4년제 졸업자와 학점은행제 106학점 이상 이수자입니다.",
              "2005년 신설, 합격률은 70~80%대, 과목당 스무 문제, 10000명"]:
        print(t, "→", to_speech(t))