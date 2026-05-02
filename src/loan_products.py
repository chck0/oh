"""정책대출 정적 룰북 — 대출상담사 에이전트의 데이터 소스.

한국 정책대출 상품의 자격·한도·금리 스냅샷을 보관한다. 외부 API를 호출하지
않고, 학기 단위로 안정적인 정적 데이터로 운용한다.

모든 수치는 출처(`source` 필드)와 기준일(`as_of` 필드)을 명시한다 —
MANIFESTO 핵심가치 1번 "모든 수치에 출처".

업데이트 절차:
1. `as_of` 갱신
2. `source` URL 확인
3. `tests/test_loan_products.py`로 스키마 검증
"""
from __future__ import annotations

# 만원 단위. 1억 = 10000.

LOAN_PRODUCTS: dict[str, dict] = {
    # ────────────────────────────────────────────────────────────
    # 디딤돌대출 — 무주택 저소득 실수요자 대상
    # ────────────────────────────────────────────────────────────
    "didimdol": {
        "name": "디딤돌대출",
        "issuer": "한국주택금융공사",
        "source": "한국주택금융공사 공식 안내 (https://www.hf.go.kr)",
        "as_of": "2025-Q1",
        "summary": "무주택 세대주 대상 저금리 정책 모기지. 생애최초·다자녀 우대.",
        "eligibility": {
            "household_status": "무주택",
            "min_age": 19,
            # 부부합산 연소득 한도 (만원)
            "max_income_manwon": 6000,
            # 생애최초·신혼·2자녀 이상 시 우대 한도
            "max_income_first_or_multichild_manwon": 7000,
            # 주택 가격 한도 (만원). 수도권 6억, 비수도권 4억
            "max_house_price_capital_manwon": 60000,
            "max_house_price_other_manwon": 40000,
        },
        "limits": {
            # 일반 한도 2.5억, 생애최초·2자녀 이상 4억
            "max_loan_manwon": 25000,
            "max_loan_first_or_multichild_manwon": 40000,
            # LTV: 일반 70%, 생애최초 80%
            "max_ltv_pct": 70,
            "max_ltv_first_buyer_pct": 80,
        },
        "interest_rate": {
            "min_pct": 2.45,
            "max_pct": 3.55,
            "note": "소득·만기별 차등. 생애최초·다자녀 우대 금리 별도.",
        },
        "term_years": [10, 15, 20, 30],
    },
    # ────────────────────────────────────────────────────────────
    # 보금자리론 — 중간소득 실수요자 대상, 디딤돌보다 한도 큼
    # ────────────────────────────────────────────────────────────
    "bogeumjari": {
        "name": "보금자리론",
        "issuer": "한국주택금융공사",
        "source": "한국주택금융공사 공식 안내 (https://www.hf.go.kr)",
        "as_of": "2025-Q1",
        "summary": "무주택·1주택 처분조건 대상 장기 고정금리 모기지.",
        "eligibility": {
            "household_status": "무주택 또는 1주택(처분조건)",
            "min_age": 19,
            "max_income_manwon": 7000,
            "max_income_first_or_multichild_manwon": 8500,
            # 보금자리는 수도권/비수도권 구분 없이 6억
            "max_house_price_capital_manwon": 60000,
            "max_house_price_other_manwon": 60000,
        },
        "limits": {
            "max_loan_manwon": 36000,
            "max_loan_first_or_multichild_manwon": 36000,
            "max_ltv_pct": 70,
            "max_ltv_first_buyer_pct": 80,
        },
        "interest_rate": {
            "min_pct": 3.95,
            "max_pct": 4.25,
            "note": "고정금리. 우대 적용 시 추가 인하.",
        },
        "term_years": [10, 15, 20, 30, 40],
    },
}

# 생애최초 주택구매자 특례 — 별도 상품이 아닌 자격
FIRST_BUYER_BENEFIT = {
    "name": "생애최초 주택구매자 특례",
    "source": "금융위원회 2024 가계대출 관리방안",
    "as_of": "2024",
    "ltv_uplift_pct": 10,  # 일반 LTV 대비 10%p 가산 (디딤돌 70→80 등)
    "max_ltv_pct": 80,     # 절대 상한
    "acquisition_tax_reduction_max_manwon": 200,
    "notes": [
        "취득세 200만원까지 감면",
        "디딤돌·보금자리에 우대 한도 적용",
        "주택가격 12억 이하 (감면 기준)",
    ],
}

# DSR (총부채원리금상환비율) 규제 — 금융감독원 가이드
DSR_LIMITS = {
    "source": "금융감독원 가계대출 관리방안",
    "as_of": "2025",
    "bank_pct": 40,            # 은행권
    "non_bank_pct": 50,        # 보험사·저축은행 등
    "stress_test_pct_buffer": 1.0,  # 스트레스 DSR 가산금리 (참고)
}


def get_product(key: str) -> dict:
    """Look up a loan product by key. Raises KeyError if unknown."""
    if key not in LOAN_PRODUCTS:
        raise KeyError(f"Unknown loan product: {key!r}")
    return LOAN_PRODUCTS[key]


def list_product_keys() -> list[str]:
    return list(LOAN_PRODUCTS.keys())


def format_source(product_key: str) -> str:
    """Build a citation string for use in agent responses."""
    p = get_product(product_key)
    return f"[출처: {p['source']}, {p['as_of']}]"
