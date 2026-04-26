"""Tests for scenario module."""
from scenario import (
    rate_sensitivity,
    vacancy_sensitivity,
    price_sensitivity,
    stress_test,
    format_sensitivity_for_agents,
    format_stress_for_agents,
    format_full_scenario_for_agents,
)
from yield_analyzer import InvestmentParams


class TestRateSensitivity:
    def test_returns_table(self, gangnam_summary):
        t = rate_sensitivity(gangnam_summary)
        assert t is not None
        assert t.variable_name == "대출금리"
        assert len(t.results) >= 4

    def test_higher_rate_lower_income(self, gangnam_summary):
        t = rate_sensitivity(gangnam_summary)
        incomes = [r.analysis.monthly_net_income for r in t.results]
        assert incomes[0] >= incomes[-1]

    def test_custom_steps(self, gangnam_summary):
        t = rate_sensitivity(gangnam_summary, steps=[0, 1.0])
        assert len(t.results) == 2


class TestVacancySensitivity:
    def test_returns_table(self, gangnam_summary):
        t = vacancy_sensitivity(gangnam_summary)
        assert t is not None
        assert len(t.results) >= 4

    def test_more_vacancy_lower_yield(self, gangnam_summary):
        t = vacancy_sensitivity(gangnam_summary)
        yields = [r.analysis.net_yield for r in t.results]
        assert yields[0] >= yields[-1]


class TestPriceSensitivity:
    def test_returns_table(self, gangnam_summary):
        t = price_sensitivity(gangnam_summary)
        assert t is not None
        assert len(t.results) >= 5

    def test_lower_price_higher_yield(self, gangnam_summary):
        t = price_sensitivity(gangnam_summary)
        first = t.results[0].analysis.gross_yield   # -20%
        last = t.results[-1].analysis.gross_yield    # +20%
        assert first > last


class TestStressTest:
    def test_returns_result(self, gangnam_summary):
        st = stress_test(gangnam_summary)
        assert st is not None
        assert st.region == "강남구"

    def test_worst_less_than_best(self, gangnam_summary):
        st = stress_test(gangnam_summary)
        assert st.worst.analysis.monthly_net_income < st.best.analysis.monthly_net_income

    def test_base_between_worst_and_best(self, gangnam_summary):
        st = stress_test(gangnam_summary)
        assert st.worst.analysis.monthly_net_income <= st.base.analysis.monthly_net_income
        assert st.base.analysis.monthly_net_income <= st.best.analysis.monthly_net_income


class TestFormatting:
    def test_sensitivity_format(self, gangnam_summary):
        t = rate_sensitivity(gangnam_summary)
        text = format_sensitivity_for_agents(t)
        assert "민감도 분석" in text
        assert "강남구" in text

    def test_stress_format(self, gangnam_summary):
        st = stress_test(gangnam_summary)
        text = format_stress_for_agents(st)
        assert "스트레스 테스트" in text
        assert "최악" in text
        assert "최선" in text

    def test_full_format(self, sample_summaries):
        text = format_full_scenario_for_agents(sample_summaries)
        assert "시나리오 시뮬레이션" in text
        assert "강남구" in text
        assert "성동구" in text
