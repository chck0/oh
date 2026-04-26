"""Tests for yield_analyzer module."""
from yield_analyzer import (
    InvestmentParams,
    YieldAnalysis,
    analyze_region,
    analyze_multi_region,
    format_analysis_for_agents,
)


class TestInvestmentParams:
    def test_defaults(self):
        p = InvestmentParams()
        assert p.ltv == 0.6
        assert p.loan_rate == 4.0
        assert p.vacancy_months == 1.0

    def test_custom(self):
        p = InvestmentParams(ltv=0.5, loan_rate=5.0)
        assert p.ltv == 0.5
        assert p.loan_rate == 5.0


class TestAnalyzeRegion:
    def test_returns_analysis(self, gangnam_summary):
        a = analyze_region(gangnam_summary)
        assert a is not None
        assert a.region == "강남구"

    def test_gross_yield_positive(self, gangnam_summary):
        a = analyze_region(gangnam_summary)
        assert a.gross_yield > 0

    def test_net_yield_less_than_gross(self, gangnam_summary):
        a = analyze_region(gangnam_summary)
        assert a.net_yield < a.gross_yield

    def test_equity_plus_loan_equals_price(self, gangnam_summary):
        a = analyze_region(gangnam_summary)
        assert a.equity + a.loan_amount == a.avg_price

    def test_acquisition_tax_positive(self, gangnam_summary):
        a = analyze_region(gangnam_summary)
        assert a.acquisition_tax > 0

    def test_higher_ltv_lower_equity(self, gangnam_summary):
        low = analyze_region(gangnam_summary, InvestmentParams(ltv=0.4))
        high = analyze_region(gangnam_summary, InvestmentParams(ltv=0.7))
        assert high.equity < low.equity

    def test_higher_rate_lower_net_income(self, gangnam_summary):
        low = analyze_region(gangnam_summary, InvestmentParams(loan_rate=3.0))
        high = analyze_region(gangnam_summary, InvestmentParams(loan_rate=6.0))
        assert high.monthly_net_income < low.monthly_net_income


class TestAnalyzeMultiRegion:
    def test_returns_all(self, sample_summaries):
        results = analyze_multi_region(sample_summaries)
        assert len(results) == 3

    def test_with_custom_params(self, sample_summaries):
        p = InvestmentParams(ltv=0.5)
        results = analyze_multi_region(sample_summaries, p)
        for r in results:
            assert r.params.ltv == 0.5


class TestFormatAnalysis:
    def test_contains_header(self, sample_summaries):
        analyses = analyze_multi_region(sample_summaries)
        text = format_analysis_for_agents(analyses)
        assert "수익률 분석" in text

    def test_contains_comparison(self, sample_summaries):
        analyses = analyze_multi_region(sample_summaries)
        text = format_analysis_for_agents(analyses)
        assert "비교 요약" in text
        assert "1위" in text

    def test_empty_returns_empty(self):
        assert format_analysis_for_agents([]) == ""
