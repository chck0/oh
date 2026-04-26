"""Tests for CEO briefing report generation."""
from briefing import generate_ceo_briefing
from pipeline import PipelineResult, run_pipeline


class TestGenerateCeoBriefing:
    def test_empty_result_returns_empty(self):
        assert generate_ceo_briefing(PipelineResult()) == ""

    def test_single_region_has_all_sections(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p, "강남 오피스텔 투자 검토")
        assert "CEO 사전 브리핑 보고서" in text
        assert "강남 오피스텔 투자 검토" in text
        assert "핵심 요약" in text
        assert "시장 현황" in text
        assert "수익률 분석" in text
        assert "리스크 시뮬레이션" in text
        assert "현금흐름" in text
        assert "세금" in text
        assert "스코어카드" in text
        assert "논의 포인트" in text

    def test_multi_region_has_portfolio(self):
        p = run_pipeline(["강남구", "성동구"])
        text = generate_ceo_briefing(p)
        assert "포트폴리오 추천" in text

    def test_single_region_no_portfolio(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p)
        assert "포트폴리오 추천" not in text

    def test_contains_region_names(self):
        p = run_pipeline(["강남구", "성동구"])
        text = generate_ceo_briefing(p)
        assert "강남구" in text
        assert "성동구" in text

    def test_sample_data_warning(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p)
        assert "샘플 데이터" in text

    def test_market_table_has_headers(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p)
        assert "평균 매매가" in text
        assert "평균 월세" in text

    def test_yield_table_has_key_metrics(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p)
        assert "순수익률" in text
        assert "레버리지" in text
        assert "손익분기" in text

    def test_monte_carlo_table(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p)
        assert "손실확률" in text
        assert "IRR 중앙값" in text

    def test_no_topic_omits_line(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p)
        assert "안건" not in text

    def test_with_topic_includes_line(self):
        p = run_pipeline(["강남구"])
        text = generate_ceo_briefing(p, "테스트 안건")
        assert "테스트 안건" in text
