"""자막 큐 시작 시각 테스트 (API 호출 없음)

실행: cd pipeline && uv run --with pytest pytest -q tests/test_subtitle.py
"""
import dataclasses
import re

import pytest

from pipeline import config
from pipeline.steps import s07_subtitle as s07
from pipeline.utils import ffmpeg as ff
from pipeline.utils.pronounce import to_speech


def _times(speech: str, step: float = 0.1) -> list[list[float]]:
    """글자마다 step초씩 (공백도 한 칸)"""
    return [[round(i * step, 3), round((i + 1) * step, 3)] for i in range(len(speech))]


@pytest.mark.parametrize("text,head", [
    ("최신판인지, NGN의 Bow-tie와 Trend가 있는지도 꼭 보셔야 합니다.", "있는지도"),   # 영어 표기가 발음보다 김
    ("포스코 뉴스룸 설문에선 서류전형 16.7%보다 인적성검사 20.1%가 더 까다로웠습니다.", "인적성검사"),  # 숫자
    ("2026년 하반기 공채는 9월 1일~16일 15시 접수입니다.", "15시"),                       # 날짜 범위
])
def test_speech_index_finds_exact_position(text, head):
    speech = to_speech(text)
    i = s07.speech_index(text, text.find(head), speech)
    assert i is not None
    assert speech[i:].startswith(to_speech(head)[:2])


def test_speech_index_mismatch_returns_none():
    text = "합격률은 70%입니다. 준비는 두 달이면 됩니다."
    speech = "합격률은 칠십 퍼센트예요. 준비는 두 달이면 됩니다."  # 읽는 문장이 다르게 만들어진 경우
    assert s07.speech_index(text, text.find("준비는"), speech) is None


def test_cue_start_uses_exact_char_time_not_ratio():
    """띄어쓰기에서 나눈 큐는 예전엔 글자 수 비율로 계산해서 영어 표기가 길면 늦게 넘어갔다"""
    text = "최신판인지, NGN의 Bow-tie와 Trend가 있는지도 꼭 보셔야 합니다."
    speech = to_speech(text)
    ct = _times(speech)
    cues = ["최신판인지,", "NGN의 Bow-tie와 Trend가", "있는지도 꼭 보셔야 합니다."]
    starts = s07._cue_starts_from_speech(text, cues, speech, ct)
    assert starts[1] == ct[speech.index("엔지엔")][0]
    assert starts[2] == ct[speech.index("있는지도")][0]


def test_lead_shifts_cues_but_not_first(monkeypatch):
    text = "첫 문장입니다. 둘째 문장입니다."
    speech = to_speech(text)
    ct = _times(speech)
    base = s07.build_srt(text, 3.0, speech, ct)
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, subtitle_lead_sec=0.1))
    led = s07.build_srt(text, 3.0, speech, ct)
    t = lambda srt: [m for m in re.findall(r"(\d\d:\d\d:\d\d,\d{3}) -->", srt)]
    assert t(base)[0] == t(led)[0] == "00:00:00,000"
    sec = lambda s: int(s[6:8]) + int(s[9:]) / 1000
    assert abs(sec(t(base)[1]) - sec(t(led)[1]) - 0.1) < 0.002


def test_ratio_fallback_uses_actual_silence():
    """글자 시각이 없으면 장면 길이에서 실제로 붙인 앞뒤 무음을 빼고 글자 수 비율로 나눈다"""
    text = "가나다라. 마바사아."
    srt = s07.build_srt(text, 2.0)
    second = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) -->", srt)[1]
    got = int(second[2]) + int(second[3]) / 1000
    speech = 2.0 - ff.LEAD_SEC - ff.TAIL_SEC - ff.KEEP_SEC
    assert abs(got - (ff.LEAD_SEC + speech * 5 / 10)) < 0.002  # 첫 큐 '가나다라.' 5글자 / 전체 10글자


@pytest.mark.parametrize("size,expected", [(36, 18), (56, 12), (96, 7)])
def test_subtitle_size_wraps_inside_safe_width(size, expected):
    text = "띄어쓰기 없는 긴 단어도 확인합니다. 가나다라마바사아자차카타파하가나다라마바사."
    chars = s07.job_style.line_chars(size)
    assert chars == expected
    srt = s07.build_srt(text, 12.0, line_chars=chars)
    lines = [block.splitlines()[2:] for block in srt.strip().split("\n\n")]
    assert all(len(cue) <= 2 and all(len(line) <= chars for line in cue) for cue in lines)
    assert "".join("".join(cue).replace(" ", "") for cue in lines) == text.replace(" ", "")
