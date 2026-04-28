"""전세 vs 매수 비교 분석기.

타겟 사용자: 전세 거주 중인 30대 직장인의 매수 의사결정 지원.

CFO(재무총괄)가 참조할 수 있도록 다음 지표를 계산:
- 월 대출 상환액 (원리금 균등상환 방식)
- DSR (총부채원리금상환비율) 추정
- 전세 보증금 기회비용 (예금 금리 기준)
- 매수 시 추가 필요 현금 (취득세 포함)
- 전세 유지 vs 매수 월 비용 비교
- 손익분기점 (몇 년 후 매수가 유리해지는가)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RentVsBuyParams:
    """전세 vs 매수 비교 파라미터."""

    property_price: int          # 매수 희망 매물 가격 (만원)
    jeonse_deposit: int          # 현재 전세 보증금 (만원)
    monthly_income: int          # 월 세전 소득 (만원) — DSR 계산용
    loan_rate: float = 4.0       # 대출 금리 (연 %, 기본 4.0)
    loan_years: int = 30         # 대출 기간 (년, 기본 30)
    ltv: float = 0.6             # 담보인정비율 (기본 60%)
    savings_rate: float = 3.5    # 예금 금리 (연 %, 기회비용 계산용)
    price_growth: float = 2.0    # 연간 집값 상승률 추정 (%)
    monthly_rent_alt: int = 0    # 동일 매물 월세 시세 (만원, 0이면 비교 생략)


@dataclass
class RentVsBuyResult:
    """전세 vs 매수 비교 분석 결과."""

    # 매수 비용
    loan_amount: int             # 대출금액 (만원)
    down_payment_needed: int     # 추가 필요 현금 (만원, 취득세 포함)
    acquisition_tax: int         # 취득세 (만원)
    monthly_payment: int         # 월 대출 상환액 (만원)
    dsr: float                   # DSR 추정 (%)

    # 전세 기회비용
    jeonse_opportunity_cost: int # 전세 보증금 예금 시 월 이자 (만원)

    # 비교
    monthly_buy_cost: int        # 매수 시 월 실질 비용 (만원)
    monthly_rent_cost: int       # 전세/월세 유지 시 월 비용 (만원)
    monthly_diff: int            # 월 비용 차이 (매수 - 전세, 양수면 매수가 비쌈)
    breakeven_years: float       # 손익분기점 (년, 집값 상승 고려)

    # 판정
    verdict: str                 # 매수 적합성 판정 메시지
    verdict_detail: list[str] = field(default_factory=list)  # 근거 상세


def analyze(params: RentVsBuyParams) -> RentVsBuyResult:
    """전세 vs 매수 비교 분석 실행."""

    p = params

    # ── 1. 대출 계산 ──────────────────────────────────────────
    loan_amount = int(p.property_price * p.ltv)
    monthly_rate = (p.loan_rate / 100) / 12
    n_months = p.loan_years * 12

    if monthly_rate > 0:
        monthly_payment = int(
            loan_amount
            * (monthly_rate * (1 + monthly_rate) ** n_months)
            / ((1 + monthly_rate) ** n_months - 1)
        )
    else:
        monthly_payment = loan_amount // n_months

    # ── 2. DSR 추정 ───────────────────────────────────────────
    # DSR = 연간 원리금 / 연 소득
    dsr = round((monthly_payment * 12) / (p.monthly_income * 12) * 100, 1)

    # ── 3. 취득세 (1주택, 6억 이하 1.1%) ──────────────────────
    if p.property_price <= 60000:   # 6억 이하
        tax_rate = 0.011
    elif p.property_price <= 90000: # 9억 이하
        tax_rate = 0.02
    else:
        tax_rate = 0.03
    acquisition_tax = int(p.property_price * tax_rate)

    # ── 4. 추가 필요 현금 ─────────────────────────────────────
    # 전세보증금은 매수 시 돌려받아 자금으로 활용
    down_payment_needed = max(
        0,
        (p.property_price - loan_amount) - p.jeonse_deposit + acquisition_tax,
    )

    # ── 5. 전세 기회비용 (월) ─────────────────────────────────
    jeonse_opportunity_cost = int(
        p.jeonse_deposit * (p.savings_rate / 100) / 12
    )

    # ── 6. 월 비용 비교 ───────────────────────────────────────
    # 매수: 대출 상환 + (추가 투입 현금 기회비용)
    extra_cash_opp = int(
        down_payment_needed * (p.savings_rate / 100) / 12
    )
    monthly_buy_cost = monthly_payment + extra_cash_opp

    # 전세 유지: 전세 보증금 기회비용 (월세라면 월세 그 자체)
    if p.monthly_rent_alt > 0:
        monthly_rent_cost = p.monthly_rent_alt
    else:
        monthly_rent_cost = jeonse_opportunity_cost

    monthly_diff = monthly_buy_cost - monthly_rent_cost

    # ── 7. 손익분기점 ─────────────────────────────────────────
    # 취득세(초기비용) ÷ 연간 절약액(월세 절약 + 집값 상승분)
    annual_price_gain = int(p.property_price * (p.price_growth / 100))
    annual_saving = (-monthly_diff * 12) + annual_price_gain  # 매수가 유리한 금액

    if annual_saving > 0:
        breakeven_years = round(acquisition_tax / annual_saving, 1)
    elif monthly_diff <= 0:
        breakeven_years = 0.0   # 즉시 매수가 유리
    else:
        breakeven_years = 99.0  # 사실상 손익분기 불가

    # ── 8. 판정 ───────────────────────────────────────────────
    verdict, verdict_detail = _judge(
        dsr=dsr,
        down_payment_needed=down_payment_needed,
        property_price=p.property_price,
        monthly_diff=monthly_diff,
        breakeven_years=breakeven_years,
    )

    return RentVsBuyResult(
        loan_amount=loan_amount,
        down_payment_needed=down_payment_needed,
        acquisition_tax=acquisition_tax,
        monthly_payment=monthly_payment,
        dsr=dsr,
        jeonse_opportunity_cost=jeonse_opportunity_cost,
        monthly_buy_cost=monthly_buy_cost,
        monthly_rent_cost=monthly_rent_cost,
        monthly_diff=monthly_diff,
        breakeven_years=breakeven_years,
        verdict=verdict,
        verdict_detail=verdict_detail,
    )


def _judge(
    dsr: float,
    down_payment_needed: int,
    property_price: int,
    monthly_diff: int,
    breakeven_years: float,
) -> tuple[str, list[str]]:
    """매수 적합성 판정 로직."""
    issues: list[str] = []

    if dsr > 40:
        issues.append(f"DSR {dsr}% — 금융감독원 권고 40% 초과. 대출 한도 제한 가능성 있음")
    if down_payment_needed > property_price * 0.3:
        issues.append(
            f"추가 필요 현금 {down_payment_needed:,}만원 — 매물가의 30% 초과. "
            "자금 계획 재검토 필요"
        )
    if breakeven_years > 10:
        issues.append(f"손익분기점 {breakeven_years}년 — 10년 초과. 장기 보유 부담")

    if not issues:
        verdict = "✅ 매수 검토 가능 — 월 상환 부담·자금 조달 모두 적정 수준"
    elif len(issues) == 1:
        verdict = "⚠️ 조건부 검토 — 아래 리스크 확인 후 판단"
    else:
        verdict = "🔴 매수 신중 — 복수의 리스크 요인 존재"

    return verdict, issues


def format_report(params: RentVsBuyParams, result: RentVsBuyResult) -> str:
    """분석 결과를 CFO 보고서 형식으로 출력."""
    r = result
    lines = [
        "■ 전세 vs 매수 비교 분석",
        f"  매물가격        : {params.property_price:>8,}만원",
        f"  대출금액 (LTV {params.ltv*100:.0f}%): {r.loan_amount:>8,}만원",
        f"  월 대출상환액   : {r.monthly_payment:>8,}만원",
        f"  DSR 추정        : {r.dsr:>7.1f}%",
        f"  취득세          : {r.acquisition_tax:>8,}만원",
        f"  추가 필요 현금  : {r.down_payment_needed:>8,}만원",
        "",
        "  ── 월 비용 비교 ──",
        f"  매수 시 월 비용 : {r.monthly_buy_cost:>8,}만원",
        f"  전세 유지 월 비용: {r.monthly_rent_cost:>7,}만원",
        f"  월 비용 차이    : {r.monthly_diff:>+8,}만원  "
        f"({'매수가 비쌈' if r.monthly_diff > 0 else '매수가 유리'})",
        f"  손익분기점      : {r.breakeven_years:>7.1f}년",
        "",
        f"  판정: {r.verdict}",
    ]
    if r.verdict_detail:
        lines.append("  근거:")
        for detail in r.verdict_detail:
            lines.append(f"    · {detail}")
    return "\n".join(lines)


# ── 빠른 데모 ──────────────────────────────────────────────────
if __name__ == "__main__":
    demo = RentVsBuyParams(
        property_price=50000,   # 5억 아파트
        jeonse_deposit=35000,   # 현재 전세 3.5억
        monthly_income=600,     # 월 소득 600만원
        loan_rate=4.0,
        monthly_rent_alt=160,   # 동일 매물 월세 160만원
    )
    result = analyze(demo)
    print(format_report(demo, result))
