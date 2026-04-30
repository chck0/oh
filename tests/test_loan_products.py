"""Schema and content sanity checks for src/loan_products.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loan_products import (
    DSR_LIMITS,
    FIRST_BUYER_BENEFIT,
    LOAN_PRODUCTS,
    format_source,
    get_product,
    list_product_keys,
)


REQUIRED_TOP_FIELDS = {
    "name",
    "issuer",
    "source",
    "as_of",
    "summary",
    "eligibility",
    "limits",
    "interest_rate",
    "term_years",
}

REQUIRED_ELIGIBILITY_FIELDS = {
    "household_status",
    "min_age",
    "max_income_manwon",
    "max_income_first_or_multichild_manwon",
    "max_house_price_capital_manwon",
    "max_house_price_other_manwon",
}

REQUIRED_LIMITS_FIELDS = {
    "max_loan_manwon",
    "max_loan_first_or_multichild_manwon",
    "max_ltv_pct",
    "max_ltv_first_buyer_pct",
}


class TestProductSchema:
    """모든 상품이 동일한 스키마를 따르는지 검증."""

    def test_has_at_least_two_products(self):
        assert len(LOAN_PRODUCTS) >= 2

    def test_didimdol_present(self):
        assert "didimdol" in LOAN_PRODUCTS

    def test_bogeumjari_present(self):
        assert "bogeumjari" in LOAN_PRODUCTS

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_required_top_fields(self, key):
        product = LOAN_PRODUCTS[key]
        missing = REQUIRED_TOP_FIELDS - set(product.keys())
        assert not missing, f"{key} missing top fields: {missing}"

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_eligibility_fields(self, key):
        elig = LOAN_PRODUCTS[key]["eligibility"]
        missing = REQUIRED_ELIGIBILITY_FIELDS - set(elig.keys())
        assert not missing, f"{key}.eligibility missing: {missing}"

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_limits_fields(self, key):
        limits = LOAN_PRODUCTS[key]["limits"]
        missing = REQUIRED_LIMITS_FIELDS - set(limits.keys())
        assert not missing, f"{key}.limits missing: {missing}"

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_interest_rate_min_le_max(self, key):
        rate = LOAN_PRODUCTS[key]["interest_rate"]
        assert rate["min_pct"] <= rate["max_pct"]
        assert 0 < rate["min_pct"] < 20  # sanity

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_term_years_nonempty(self, key):
        terms = LOAN_PRODUCTS[key]["term_years"]
        assert len(terms) > 0
        assert all(isinstance(t, int) and t > 0 for t in terms)

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_first_buyer_uplift_not_smaller(self, key):
        """생애최초/다자녀 우대 한도는 일반 한도 이상이어야 한다."""
        limits = LOAN_PRODUCTS[key]["limits"]
        assert (
            limits["max_loan_first_or_multichild_manwon"]
            >= limits["max_loan_manwon"]
        )
        assert (
            limits["max_ltv_first_buyer_pct"]
            >= limits["max_ltv_pct"]
        )

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_first_buyer_income_uplift_not_smaller(self, key):
        elig = LOAN_PRODUCTS[key]["eligibility"]
        assert (
            elig["max_income_first_or_multichild_manwon"]
            >= elig["max_income_manwon"]
        )

    @pytest.mark.parametrize("key", list(LOAN_PRODUCTS.keys()))
    def test_source_and_as_of_present(self, key):
        p = LOAN_PRODUCTS[key]
        assert p["source"]
        assert p["as_of"]


class TestFirstBuyerBenefit:
    def test_ltv_uplift_positive(self):
        assert FIRST_BUYER_BENEFIT["ltv_uplift_pct"] > 0

    def test_max_ltv_capped(self):
        assert FIRST_BUYER_BENEFIT["max_ltv_pct"] <= 100

    def test_has_source(self):
        assert FIRST_BUYER_BENEFIT["source"]


class TestDSRLimits:
    def test_bank_lt_non_bank(self):
        """은행권 DSR이 2금융권보다 보수적이어야 한다."""
        assert DSR_LIMITS["bank_pct"] <= DSR_LIMITS["non_bank_pct"]

    def test_bank_in_reasonable_range(self):
        assert 30 <= DSR_LIMITS["bank_pct"] <= 50


class TestHelpers:
    def test_get_product_returns_dict(self):
        p = get_product("didimdol")
        assert p["name"] == "디딤돌대출"

    def test_get_product_unknown_raises(self):
        with pytest.raises(KeyError):
            get_product("nonexistent")

    def test_list_product_keys(self):
        keys = list_product_keys()
        assert "didimdol" in keys
        assert "bogeumjari" in keys

    def test_format_source_includes_as_of(self):
        s = format_source("didimdol")
        assert "[출처:" in s
        assert "2025" in s
