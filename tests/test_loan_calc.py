"""Unit tests for src/loan_calc.py — LTV/DTI/DSR + 정책대출 자격 판정."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loan_calc import (
    LoanContext,
    ProductEvaluation,
    Qualification,
    calc_dsr_pct,
    calc_ltv_pct,
    disqualified_products,
    evaluate_product,
    max_loan_by_dsr,
    max_loan_by_ltv,
    monthly_payment_manwon,
    qualify_product,
    recommend_products,
)


# ────────────────────────────────────────────────────────────
# Core math
# ────────────────────────────────────────────────────────────


class TestMonthlyPayment:
    def test_zero_principal_returns_zero(self):
        assert monthly_payment_manwon(0, 3.5, 30) == 0

    def test_zero_term_returns_zero(self):
        assert monthly_payment_manwon(30000, 3.5, 0) == 0

    def test_zero_rate_is_principal_over_months(self):
        # 3억 / 360개월 = 833만원 ... 실제로는 약 83만원/월. 단위가 만원이므로 30000/360≈83.
        assert monthly_payment_manwon(30000, 0, 30) == round(30000 / 360)

    def test_known_value_3_8_pct_30y(self):
        # 4억 8천 (생애최초 LTV 80%, 6억 매물) @ 3.8%, 30년 → 약 224만원
        # P = 48000 * (r(1+r)^n)/((1+r)^n - 1), r=0.0316667%, n=360
        result = monthly_payment_manwon(48000, 3.8, 30)
        assert 220 <= result <= 230, f"expected ~225, got {result}"

    def test_higher_rate_means_higher_payment(self):
        low = monthly_payment_manwon(30000, 3.0, 30)
        high = monthly_payment_manwon(30000, 5.0, 30)
        assert high > low

    def test_longer_term_means_lower_monthly(self):
        short = monthly_payment_manwon(30000, 4.0, 15)
        long_ = monthly_payment_manwon(30000, 4.0, 30)
        assert long_ < short


class TestLTV:
    def test_basic(self):
        # 4.2억 대출 / 6억 매물 = 70%
        assert calc_ltv_pct(42000, 60000) == pytest.approx(70.0)

    def test_zero_price_returns_zero(self):
        assert calc_ltv_pct(10000, 0) == 0.0

    def test_max_loan_by_ltv_70pct(self):
        assert max_loan_by_ltv(60000, 70) == 42000

    def test_max_loan_by_ltv_80pct_first_buyer(self):
        assert max_loan_by_ltv(60000, 80) == 48000


class TestDSR:
    def test_basic(self):
        # 월 200 부담 / 월 500 소득 = 40%
        assert calc_dsr_pct(200, 0, 6000) == pytest.approx(40.0)

    def test_with_existing_debt(self):
        # 월 100 신규 + 월 50 기존 = 150 / 500 = 30%
        assert calc_dsr_pct(100, 50, 6000) == pytest.approx(30.0)

    def test_zero_income_returns_zero(self):
        assert calc_dsr_pct(200, 0, 0) == 0.0

    def test_max_loan_by_dsr_zero_income(self):
        assert max_loan_by_dsr(0, 40, 3.8, 30) == 0

    def test_max_loan_by_dsr_basic(self):
        # 연소득 6000만 → 월 500. DSR 40% → 월 200. 3.8%/30년 → 약 4280만원
        result = max_loan_by_dsr(6000, 40, 3.8, 30)
        # 월 200 → P = 200 / factor
        # factor at 3.8%/30y ≈ 0.004665
        # P ≈ 42870
        assert 40000 <= result <= 46000

    def test_existing_debt_reduces_max(self):
        no_debt = max_loan_by_dsr(6000, 40, 3.8, 30, monthly_existing_debt_manwon=0)
        with_debt = max_loan_by_dsr(6000, 40, 3.8, 30, monthly_existing_debt_manwon=50)
        assert with_debt < no_debt

    def test_overload_returns_zero(self):
        # 기존 부채가 이미 DSR을 초과하면 0
        result = max_loan_by_dsr(6000, 40, 3.8, 30, monthly_existing_debt_manwon=300)
        assert result == 0


# ────────────────────────────────────────────────────────────
# Qualification
# ────────────────────────────────────────────────────────────


class TestQualifyDidimdol:
    def test_typical_first_buyer_qualifies(self):
        ctx = LoanContext(
            house_price_manwon=50000,    # 5억 (수도권 6억 한도 내)
            annual_income_manwon=5000,   # 부부합산 5천 (디딤돌 6천 이내)
            is_first_buyer=True,
            is_homeless=True,
            is_capital_area=True,
        )
        q = qualify_product(ctx, "didimdol")
        assert q.eligible
        assert q.reasons == []

    def test_high_income_disqualifies(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=10000,  # 1억 — 디딤돌 한도 초과
            is_first_buyer=True,
            is_homeless=True,
        )
        q = qualify_product(ctx, "didimdol")
        assert not q.eligible
        assert any("연소득" in r for r in q.reasons)

    def test_first_buyer_uplift_extends_income_cap(self):
        # 6500만원: 일반 6000 초과지만 생애최초/다자녀 7000 이내
        ctx_first = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=6500,
            is_first_buyer=True,
            is_homeless=True,
        )
        assert qualify_product(ctx_first, "didimdol").eligible

        ctx_not_first = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=6500,
            is_first_buyer=False,
            has_multi_child=False,
            is_homeless=True,
        )
        assert not qualify_product(ctx_not_first, "didimdol").eligible

    def test_high_house_price_disqualifies_capital(self):
        ctx = LoanContext(
            house_price_manwon=70000,   # 7억 — 수도권 6억 초과
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
            is_capital_area=True,
        )
        q = qualify_product(ctx, "didimdol")
        assert not q.eligible
        assert any("주택가격" in r for r in q.reasons)

    def test_non_capital_area_lower_price_cap(self):
        # 4.5억은 수도권 6억 OK, 비수도권 4억 초과
        ctx = LoanContext(
            house_price_manwon=45000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
            is_capital_area=False,
        )
        q = qualify_product(ctx, "didimdol")
        assert not q.eligible

    def test_underage_disqualifies(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            age=18,
            is_first_buyer=True,
            is_homeless=True,
        )
        q = qualify_product(ctx, "didimdol")
        assert not q.eligible
        assert any("연령" in r for r in q.reasons)

    def test_zero_income_skips_income_check(self):
        """소득 미입력(=0)이면 다른 요건은 살펴보되 소득 사유로 떨어뜨리지 않는다."""
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=0,
            is_first_buyer=True,
            is_homeless=True,
        )
        q = qualify_product(ctx, "didimdol")
        assert q.eligible


class TestQualifyBogeumjari:
    def test_typical_qualifies(self):
        ctx = LoanContext(
            house_price_manwon=55000,
            annual_income_manwon=6500,  # 보금자리 일반 7000 이내
            is_first_buyer=False,
            is_homeless=True,
        )
        q = qualify_product(ctx, "bogeumjari")
        assert q.eligible


# ────────────────────────────────────────────────────────────
# Evaluation
# ────────────────────────────────────────────────────────────


class TestEvaluateProduct:
    def test_first_buyer_uses_uplift_ltv(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        ev = evaluate_product(ctx, "didimdol")
        assert ev.applicable_ltv_pct == 80
        # 5억 * 80% = 4억
        assert ev.ltv_limited_loan_manwon == 40000

    def test_non_first_buyer_uses_base_ltv(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5500,
            is_first_buyer=False,
            is_homeless=True,
        )
        ev = evaluate_product(ctx, "didimdol")
        assert ev.applicable_ltv_pct == 70

    def test_final_is_min_of_constraints(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        ev = evaluate_product(ctx, "didimdol")
        # final은 LTV(40000), 상품한도(40000 생애최초), DSR 셋 중 최소
        assert ev.final_max_loan_manwon <= ev.ltv_limited_loan_manwon
        assert ev.final_max_loan_manwon <= ev.applicable_max_loan_manwon

    def test_own_funds_required_is_price_minus_loan(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        ev = evaluate_product(ctx, "didimdol")
        assert ev.own_funds_required_manwon == 50000 - ev.final_max_loan_manwon

    def test_monthly_payment_consistent(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        ev = evaluate_product(ctx, "didimdol")
        expected = monthly_payment_manwon(
            ev.final_max_loan_manwon, ev.interest_rate_pct, ev.term_years
        )
        assert ev.monthly_payment_manwon == expected

    def test_dsr_zero_when_no_income(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=0,
            is_first_buyer=True,
            is_homeless=True,
        )
        ev = evaluate_product(ctx, "didimdol")
        assert ev.dsr_pct == 0.0

    def test_source_includes_as_of(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        ev = evaluate_product(ctx, "didimdol")
        assert "한국주택금융공사" in ev.source
        assert "2025" in ev.source


# ────────────────────────────────────────────────────────────
# Recommendation
# ────────────────────────────────────────────────────────────


class TestRecommendProducts:
    def test_returns_eligible_only_sorted_by_rate(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        recs = recommend_products(ctx)
        # 디딤돌(2.45~3.55) + 보금자리(3.95~4.25) 둘 다 적격
        assert len(recs) == 2
        # 금리 낮은 순
        rates = [r.interest_rate_pct for r in recs]
        assert rates == sorted(rates)
        assert recs[0].product_key == "didimdol"

    def test_high_income_excludes_didimdol(self):
        ctx = LoanContext(
            house_price_manwon=55000,
            annual_income_manwon=8000,  # 디딤돌 7000(우대) 초과, 보금자리 8500(우대) 이내
            is_first_buyer=True,
            is_homeless=True,
        )
        recs = recommend_products(ctx)
        keys = {r.product_key for r in recs}
        assert "didimdol" not in keys
        assert "bogeumjari" in keys

    def test_all_disqualified_returns_empty(self):
        ctx = LoanContext(
            house_price_manwon=80000,    # 8억 — 모두 6억 초과
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        assert recommend_products(ctx) == []


class TestDisqualifiedProducts:
    def test_returns_only_failed(self):
        ctx = LoanContext(
            house_price_manwon=80000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        dq = disqualified_products(ctx)
        # 둘 다 주택가격 초과로 떨어짐
        assert len(dq) == 2
        for q in dq:
            assert not q.eligible
            assert q.reasons

    def test_empty_when_all_pass(self):
        ctx = LoanContext(
            house_price_manwon=50000,
            annual_income_manwon=5000,
            is_first_buyer=True,
            is_homeless=True,
        )
        # 둘 다 통과하므로 disqualified는 비어있음
        assert disqualified_products(ctx) == []
