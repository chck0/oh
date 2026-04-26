"""Tests for source_validator (Phase B.1)."""
import pytest

from source_validator import (
    SourceWarning,
    find_numbers,
    has_source_marker,
    split_sentences,
    validate_text,
)


class TestSplitSentences:
    def test_empty(self):
        assert split_sentences("") == []

    def test_single_sentence(self):
        assert split_sentences("수익률 5%입니다.") == ["수익률 5%입니다."]

    def test_multiple_sentences(self):
        text = "수익률 5%입니다. 출처는 KB입니다."
        sentences = split_sentences(text)
        assert len(sentences) == 2
        assert "수익률 5%" in sentences[0]
        assert "출처는 KB" in sentences[1]

    def test_question_and_exclamation_split(self):
        text = "정말요? 그럴 리가! 다시 봅시다."
        assert len(split_sentences(text)) == 3

    def test_strips_outer_whitespace(self):
        assert split_sentences("  수익률 5%.  ") == ["수익률 5%."]

    def test_decimal_does_not_split(self):
        # "5.5%" 의 마침표는 소수점이지 문장 종결이 아님
        text = "수익률은 5.5%입니다."
        assert len(split_sentences(text)) == 1

    def test_newline_after_period_splits(self):
        text = "수익률 5%입니다.\n[출처: KB]"
        sentences = split_sentences(text)
        assert len(sentences) == 2


class TestFindNumbers:
    def test_percent(self):
        assert "5%" in find_numbers("수익률 5% 정도")

    def test_percent_with_decimal(self):
        assert "4.2%" in find_numbers("수익률 4.2%")

    def test_percent_p(self):
        assert "0.5%p" in find_numbers("금리 0.5%p 인상")

    def test_manwon(self):
        assert "1500만원" in find_numbers("월세 1500만원")

    def test_eok_won(self):
        assert "4.5억원" in find_numbers("매매가 4.5억원")

    def test_won(self):
        assert "1000원" in find_numbers("관리비 1000원")

    def test_bae(self):
        assert "2배" in find_numbers("위험이 2배")

    def test_decimal_with_comma(self):
        results = find_numbers("4,500만원 입니다")
        assert any("4,500" in r for r in results)

    def test_excluded_units_no_match(self):
        # 프로필/기간/범용 단위는 의도적으로 검출하지 않음 (오탐 방지)
        assert find_numbers("1주택자입니다") == []
        assert find_numbers("5년 보유 계획") == []
        assert find_numbers("매물 3건") == []
        assert find_numbers("공실 2개월") == []

    def test_no_numbers(self):
        assert find_numbers("그냥 텍스트입니다.") == []

    def test_multiple_numbers_in_one_sentence(self):
        nums = find_numbers("표면 3% 실질 1.8% 모두")
        assert "3%" in nums
        assert "1.8%" in nums


class TestHasSourceMarker:
    def test_basic_source(self):
        assert has_source_marker("[출처: KB부동산]")

    def test_source_with_space_before_colon(self):
        assert has_source_marker("[출처 : KB]")

    def test_estimate_marker(self):
        assert has_source_marker("이건 [추정] 수치")

    def test_assumption_marker(self):
        assert has_source_marker("[가정 LTV 60%]")

    def test_profile_marker(self):
        assert has_source_marker("[프로필] 사용자 예산")

    def test_no_marker(self):
        assert not has_source_marker("출처 없는 그냥 텍스트")

    def test_paren_form_not_recognized(self):
        # 페르소나 명세상 대괄호 형식만 정식
        assert not has_source_marker("(출처: KB)")


class TestValidateText:
    def test_passes_with_source(self):
        text = "수익률은 4.2%입니다 [출처: 한국은행]."
        assert validate_text(text) == []

    def test_warns_without_source(self):
        text = "수익률은 4.2%입니다."
        warnings = validate_text(text)
        assert len(warnings) == 1
        assert warnings[0].rule == "missing_source"
        assert "4.2%" in warnings[0].message

    def test_one_marker_covers_all_numbers_in_sentence(self):
        text = "표면 3% 실질 1.8% 모두 같은 출처 [출처: KB]."
        assert validate_text(text) == []

    def test_separate_sentences_need_separate_sources(self):
        text = "수익률 4.2%입니다 [출처: KB]. 취득세는 4.6%입니다."
        warnings = validate_text(text)
        assert len(warnings) == 1
        assert "4.6%" in warnings[0].message

    def test_text_without_numbers_passes(self):
        text = "전반적으로 검토 의견입니다. 추가 데이터가 필요합니다."
        assert validate_text(text) == []

    def test_estimate_marker_passes(self):
        text = "약 4억원 수준 [추정]."
        assert validate_text(text) == []

    def test_assumption_marker_passes(self):
        text = "LTV 60% 기준입니다 [가정 LTV 60%]."
        assert validate_text(text) == []

    def test_profile_marker_passes(self):
        text = "예산 4.5억원 기준입니다 [프로필]."
        assert validate_text(text) == []

    def test_empty_text(self):
        assert validate_text("") == []

    def test_long_snippet_truncated(self):
        long = "수익률 5% " + "긴 문장 단어 " * 20 + "."
        warnings = validate_text(long)
        assert len(warnings) == 1
        assert len(warnings[0].snippet) <= 80

    def test_warning_str_format(self):
        warnings = validate_text("수익률 5%.")
        assert "[missing_source]" in str(warnings[0])

    def test_profile_units_dont_warn(self):
        # 사용자 프로필 인용은 출처 없어도 OK (검출 단위 자체에서 제외)
        text = "1주택자이시고 5년 보유 계획입니다."
        assert validate_text(text) == []

    def test_realistic_cfo_response_passes(self):
        text = (
            "대표님, 강남 오피스텔 표면 수익률 3%는 "
            "관리비·공실·세금 빼면 실질 1.8~2.2%입니다 "
            "[출처: 한국부동산원, 2025]. "
            "대출 60% 끼면 레버리지 4.2% 찍히지만 "
            "취득세 4.6% 떼면 첫해 마이너스예요 [출처: 지방세법]."
        )
        assert validate_text(text) == []

    def test_realistic_cfo_response_with_missing_source_warns(self):
        text = (
            "대표님, 강남 표면 3%는 실질 1.8%입니다 [출처: 한국부동산원]. "
            "대출 60% 끼면 레버리지 4.2% 찍힙니다."
        )
        warnings = validate_text(text)
        assert len(warnings) == 1
        assert "4.2%" in warnings[0].message


class TestSourceWarning:
    def test_dataclass_fields(self):
        w = SourceWarning(rule="missing_source", message="msg", snippet="sn")
        assert w.rule == "missing_source"
        assert w.message == "msg"
        assert w.snippet == "sn"

    def test_frozen(self):
        w = SourceWarning(rule="r", message="m", snippet="s")
        with pytest.raises(Exception):  # FrozenInstanceError
            w.rule = "x"  # type: ignore[misc]
