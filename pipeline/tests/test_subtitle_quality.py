"""자막 품질 검사 (API 호출 없음).

예문은 실제로 만든 영상에서 어색하게 끊겼던 자막이다.
"""
from pipeline.schema import SceneDraft, ScriptDraft
from pipeline.steps.s03_script import _focus_error, _violations
from pipeline.steps.s07_subtitle import build_srt, max_cue_chars, split_cues, wrap_two_lines


def lines(cue: str, line_chars: int = 19) -> list[str]:
    return wrap_two_lines(cue, line_chars).split("\n")


# ---------- 줄 나누기 ----------
def test_compound_noun_not_split():
    # 이전: "현실적인 주거 / 문제가 더 선명해집니다."
    assert lines("현실적인 주거 문제가 더 선명해집니다.") == ["현실적인 주거 문제가", "더 선명해집니다."]


def test_noun_phrase_not_split():
    # 이전: "전문 이론과 실무로 문제 / 해결 능력을 봅니다."
    assert lines("전문 이론과 실무로 문제 해결 능력을 봅니다.") == ["전문 이론과 실무로", "문제 해결 능력을 봅니다."]


def test_modifier_stays_with_noun():
    # 이전: "작동 원리와 기술적 / 특징을 이해해 보세요."
    assert lines("작동 원리와 기술적 특징을 이해해 보세요.") == ["작동 원리와 기술적 특징을", "이해해 보세요."]


def test_adnominal_neun_after_final_consonant():
    # '묻는'은 주제 조사가 아니라 뒤 말을 꾸미므로 그 뒤에서 끊지 않는다
    for line in lines("구조와 정비 기초를 묻는 국가기술자격입니다."):
        assert not line.endswith("묻는")


def test_lines_fit_width():
    for size in (15, 19, 24):
        for cue in split_cues("결국 햇빛조차 제대로 안 드는 지하 2층 집으로 이사합니다. "
                              "현실적인 주거 문제가 더 선명해집니다.", max_cue_chars(size)):
            assert all(len(line) <= size for line in lines(cue, size)), (size, cue)


def test_number_comma_kept():
    assert split_cues("응시료는 15,000원이고 합격 기준은 60점 이상입니다.", 30)[0].startswith("응시료는 15,000원")


def test_build_srt_uses_line_chars():
    # 글씨가 커서 한 줄에 12자만 들어가면 자막도 그에 맞춰 짧게 나뉜다
    srt = build_srt("두 사람은 대출로 마련한 집에서 시작했지만, 전세 사기로 집 보증금을 잃습니다.", 6.0, line_chars=12)
    texts = [b.split("\n")[2:] for b in srt.strip().split("\n\n")]
    assert all(len(line) <= 12 for block in texts for line in block)


# ---------- 그림과 자막 맞추기 ----------
def test_focus_must_be_in_subtitle():
    sub = "결국 햇빛조차 제대로 안 드는 지하 2층 집으로 이사합니다."
    assert _focus_error("지하 2층 집", sub) is None
    assert _focus_error("지하2층 집", sub) is None  # 띄어쓰기는 무시
    assert _focus_error("고객센터", sub)          # 자막에 없는 대상
    assert _focus_error("", sub)                  # 비어 있음
    assert _focus_error(sub, sub)                 # 문장 전체를 옮긴 경우


def test_violations_report_focus():
    scene = dict(narration="결국 햇빛조차 안 드는 지하 이층 집으로 이사합니다.",
                 subtitle_text="결국 햇빛조차 안 드는 지하 2층 집으로 이사합니다.",
                 point_ids=[1], image_prompt="a couple carrying boxes down to a dark basement room")
    ok = ScriptDraft(scenes=[SceneDraft(visual_focus="지하 2층 집", **scene)])
    bad = ScriptDraft(scenes=[SceneDraft(visual_focus="웹툰 작가", **scene)])
    assert not [e for e in _violations(ok, 1, (0, 999)) if "visual_focus" in e]
    assert [e for e in _violations(bad, 1, (0, 999)) if "visual_focus" in e]


def test_long_word_without_spaces_terminates():
    # 띄어쓰기 없는 낱말이 한 줄보다 길어도 멈추지 않고 두 줄 안으로 나뉜다 (예전에는 같은 조각을 끝없이 다시 나눔)
    for size in (7, 12, 19):
        cues = split_cues("가나다라마바사아자차카타파하가나다라마바사.", max_cue_chars(size), line_chars=size)
        assert "".join(cues) == "가나다라마바사아자차카타파하가나다라마바사."
        assert all(len(line) <= size for cue in cues for line in wrap_two_lines(cue, size).split("\n"))
