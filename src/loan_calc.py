"""LTV/DTI/DSR 계산 + 정책대출 자격 판정.

대출상담사 에이전트가 BuyerProfile 기반으로 4번째 관점("공적 한도선") 예산을
산출할 때 사용하는 순수 계산 모듈. LLM 호출 없이 결정론적으로 동작.

만원 단위 정수를 기본 화폐 단위로 사용한다 (BuyerProfile과 일관).
백분율은 정수 또는 float pct (40 = 40%)로 표기.

핵심 함수:
- monthly_payment_manwon: 원리금균등 월 납입액 계산
- max_loan_by_ltv: LTV 상한 기준 최대 대출
- max_loan_by_dsr: DSR 상한 기준 최대 대출 (월 가용 원리금 역산)
- qualify_product: 정책대출 자격 판정
- evaluate_product: 자격 통과 시 한도/금리/월 부담 산출
- recommend_products: 적용 가능한 정책대출 순위 (낮은 금리 우선)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loan_products import (
    DSR_LIMITS,
    FIRST_BUYER_BENEFIT,
    LOAN_PRODUCTS,
    get_product,
)


# ────────────────────────────────────────────────────────────
# Inputs
# ────────────────────────────────────────────────────────────


@dataclass
class LoanContext:
    """정책대출 자격 판정·한도 계산에 필요한 입력.

    BuyerProfile에서 추출되거나, 인터뷰에서 추가로 받은 정보를 담는다.
    `annual_income_manwon=0`이면 소득 미입력으로 간주한다.
    """

    house_price_manwon: int                    # 매매가 (LTV 산정 기준)
    own_funds_manwon: int = 0                  # 자기자본
    annual_income_manwon: int = 0              # 부부합산 연소득
    monthly_existing_debt_manwon: int = 0      # 기존 월 원리금 부담
    is_first_buyer: bool = True                # 생애최초 여부
    is_homeless: bool = True                   # 무주택 여부
    has_multi_child: bool = False              # 2자녀 이상
    is_capital_area: bool = True               # 수도권 여부
    age: int = 30                              # 신청자 만 나이


# ────────────────────────────────────────────────────────────
# Core math
# ────────────────────────────────────────────────────────────


def monthly_payment_manwon(
    principal_manwon: int,
    annual_rate_pct: float,
    term_years: int,
) -> int:
    """원리금균등 월 납입액 (만원, 반올림).

    P = L * (r(1+r)^n) / ((1+r)^n - 1)
    where r = monthly rate, n = total months.

    rate=0인 경우는 원금을 균등분할.
    """
    if principal_manwon <= 0 or term_years <= 0:
        return 0
    n = term_years * 12
    if annual_rate_pct <= 0:
        return round(principal_manwon / n)
    r = annual_rate_pct / 100 / 12
    factor = (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return round(principal_manwon * factor)


def calc_ltv_pct(loan_manwon: int, house_price_manwon: int) -> float:
    """LTV 비율 (%)."""
    if house_price_manwon <= 0:
        return 0.0
    return loan_manwon / house_price_manwon * 100


def calc_dsr_pct(
    monthly_payment_manwon: int,
    monthly_existing_debt_manwon: int,
    annual_income_manwon: int,
) -> float:
    """DSR 비율 (%). 소득 0이면 0 반환 (불가측)."""
    if annual_income_manwon <= 0:
        return 0.0
    monthly_income = annual_income_manwon / 12
    total_monthly = monthly_payment_manwon + monthly_existing_debt_manwon
    return total_monthly / monthly_income * 100


def max_loan_by_ltv(
    house_price_manwon: int,
    ltv_pct: float,
) -> int:
    """LTV 상한 기준 최대 대출 가능액 (만원)."""
    return int(house_price_manwon * ltv_pct / 100)


def max_loan_by_dsr(
    annual_income_manwon: int,
    dsr_pct: float,
    annual_rate_pct: float,
    term_years: int,
    monthly_existing_debt_manwon: int = 0,
) -> int:
    """DSR 상한 내에서 가능한 최대 대출 원금 (만원).

    월 가용 원리금 = (연소득/12) * DSR% - 기존 월 부채
    원금 = 월 가용 원리금 / 월별 환산계수
    """
    if annual_income_manwon <= 0 or term_years <= 0:
        return 0
    monthly_income = annual_income_manwon / 12
    available_monthly = monthly_income * (dsr_pct / 100) - monthly_existing_debt_manwon
    if available_monthly <= 0:
        return 0
    n = term_years * 12
    if annual_rate_pct <= 0:
        return int(available_monthly * n)
    r = annual_rate_pct / 100 / 12
    factor = (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return int(available_monthly / factor)


# ────────────────────────────────────────────────────────────
# Policy loan qualification
# ────────────────────────────────────────────────────────────


@dataclass
class Qualification:
    """자격 판정 결과."""

    product_key: str
    eligible: bool
    reasons: list[str] = field(default_factory=list)  # 부적격 사유 (eligible=False일 때)


def qualify_product(ctx: LoanContext, product_key: str) -> Qualification:
    """정책대출 자격 판정. eligible=False면 reasons에 이유를 적는다."""
    p = get_product(product_key)
    elig = p["eligibility"]
    reasons: list[str] = []

    # 무주택 요건
    if "무주택" in elig["household_status"] and not ctx.is_homeless:
        if "1주택" not in elig["household_status"]:
            reasons.append("무주택 요건 미충족")

    # 나이
    if ctx.age < elig["min_age"]:
        reasons.append(f"신청 가능 연령({elig['min_age']}세) 미달")

    # 소득 한도 — 생애최초/다자녀 우대 적용 가능 여부 확인
    use_uplift = ctx.is_first_buyer or ctx.has_multi_child
    income_cap = (
        elig["max_income_first_or_multichild_manwon"]
        if use_uplift
        else elig["max_income_manwon"]
    )
    if ctx.annual_income_manwon > 0 and ctx.annual_income_manwon > income_cap:
        reasons.append(
            f"연소득 한도({income_cap:,}만원) 초과 — 입력값 {ctx.annual_income_manwon:,}만원"
        )

    # 주택가격 한도
    price_cap = (
        elig["max_house_price_capital_manwon"]
        if ctx.is_capital_area
        else elig["max_house_price_other_manwon"]
    )
    if ctx.house_price_manwon > price_cap:
        reasons.append(
            f"주택가격 한도({price_cap:,}만원) 초과 — 입력값 {ctx.house_price_manwon:,}만원"
        )

    return Qualification(
        product_key=product_key,
        eligible=not reasons,
        reasons=reasons,
    )


# ────────────────────────────────────────────────────────────
# Product evaluation (LTV·DSR 결합 한도 + 월 부담)
# ────────────────────────────────────────────────────────────


@dataclass
class ProductEvaluation:
    """자격 통과한 상품에 대한 한도·월부담 평가."""

    product_key: str
    product_name: str
    applicable_ltv_pct: float          # 생애최초 우대 반영
    applicable_max_loan_manwon: int    # 상품별 한도 (생애최초/다자녀 우대 반영)
    ltv_limited_loan_manwon: int       # LTV 상한 기준
    dsr_limited_loan_manwon: int       # DSR 상한 기준 (소득 미입력 시 0)
    final_max_loan_manwon: int         # 위 셋의 최솟값
    interest_rate_pct: float           # 적용 금리 (보수적으로 max 사용)
    term_years: int                    # 대표 만기
    monthly_payment_manwon: int        # 월 원리금 (final_max_loan 기준)
    dsr_pct: float                     # 결과 DSR (소득 미입력 시 0)
    own_funds_required_manwon: int     # 매매가 - 대출
    source: str                        # 출처 표기


def evaluate_product(
    ctx: LoanContext,
    product_key: str,
    *,
    term_years: int = 30,
    use_max_rate: bool = True,
) -> ProductEvaluation:
    """자격이 통과되었다는 가정 하에 상품 한도/월부담을 평가.

    use_max_rate=True면 보수적으로 금리 상단을 사용한다 (실제 적용 금리는
    소득별 차등이라 보수적 추정이 안전).
    """
    p = get_product(product_key)
    limits = p["limits"]
    rate_info = p["interest_rate"]

    # LTV 우대 적용
    if ctx.is_first_buyer:
        applicable_ltv = float(limits["max_ltv_first_buyer_pct"])
        # 절대 상한 (생애최초 특례)
        applicable_ltv = min(applicable_ltv, FIRST_BUYER_BENEFIT["max_ltv_pct"])
    else:
        applicable_ltv = float(limits["max_ltv_pct"])

    # 상품별 한도 (생애최초/다자녀 우대)
    use_uplift = ctx.is_first_buyer or ctx.has_multi_child
    applicable_max = (
        limits["max_loan_first_or_multichild_manwon"]
        if use_uplift
        else limits["max_loan_manwon"]
    )

    # 적용 금리 (보수적 = 상단)
    rate = rate_info["max_pct"] if use_max_rate else rate_info["min_pct"]

    # 한도 3종 비교
    ltv_limited = max_loan_by_ltv(ctx.house_price_manwon, applicable_ltv)
    if ctx.annual_income_manwon > 0:
        dsr_limited = max_loan_by_dsr(
            ctx.annual_income_manwon,
            DSR_LIMITS["bank_pct"],
            rate,
            term_years,
            ctx.monthly_existing_debt_manwon,
        )
    else:
        dsr_limited = 0

    # final = min(ltv, applicable_max, [dsr if 소득 입력됨])
    candidates = [ltv_limited, applicable_max]
    if dsr_limited > 0:
        candidates.append(dsr_limited)
    final = min(candidates)

    monthly = monthly_payment_manwon(final, rate, term_years)
    dsr = calc_dsr_pct(monthly, ctx.monthly_existing_debt_manwon, ctx.annual_income_manwon)
    own_funds_required = max(0, ctx.house_price_manwon - final)

    return ProductEvaluation(
        product_key=product_key,
        product_name=p["name"],
        applicable_ltv_pct=applicable_ltv,
        applicable_max_loan_manwon=applicable_max,
        ltv_limited_loan_manwon=ltv_limited,
        dsr_limited_loan_manwon=dsr_limited,
        final_max_loan_manwon=final,
        interest_rate_pct=rate,
        term_years=term_years,
        monthly_payment_manwon=monthly,
        dsr_pct=dsr,
        own_funds_required_manwon=own_funds_required,
        source=f"{p['source']}, {p['as_of']}",
    )


def recommend_products(
    ctx: LoanContext,
    *,
    term_years: int = 30,
) -> list[ProductEvaluation]:
    """적용 가능한 정책대출을 금리 낮은 순으로 정렬해 반환.

    부적격 상품은 제외. 모두 부적격이면 빈 리스트.
    """
    out: list[ProductEvaluation] = []
    for key in LOAN_PRODUCTS:
        if qualify_product(ctx, key).eligible:
            out.append(evaluate_product(ctx, key, term_years=term_years))
    out.sort(key=lambda e: e.interest_rate_pct)
    return out


def disqualified_products(ctx: LoanContext) -> list[Qualification]:
    """부적격 상품과 이유를 반환 (사용자에게 "왜 안 되는지" 설명용)."""
    return [
        q
        for key in LOAN_PRODUCTS
        if not (q := qualify_product(ctx, key)).eligible
    ]
