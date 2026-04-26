"""수익률 분석기 — 오피스텔 투자 수익률 자동 계산.

CFO(재무총괄)가 참조할 수 있도록 다음 지표를 계산:
- 표면 수익률 (gross yield)
- 실질 수익률 (net yield): 관리비·공실·세금 차감
- 레버리지 수익률: 대출 감안 자기자본 기준
- 월 순수익 / 연 순수익
- 손익분기점 분석
- 권역 간 비교표
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from real_estate import RegionSummary


def compute_npv(cash_flows: list[float], rate: float) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))


def compute_irr(cash_flows: list[float], tol: float = 1e-6, max_iter: int = 200) -> float:
    if not cash_flows or all(cf <= 0 for cf in cash_flows):
        return float("-inf")
    if all(cf >= 0 for cf in cash_flows):
        return float("inf")
    r = 0.1
    for _ in range(max_iter):
        npv = compute_npv(cash_flows, r)
        dnpv = sum(-t * cf / (1 + r) ** (t + 1) for t, cf in enumerate(cash_flows))
        if abs(dnpv) < 1e-12:
            break
        r_new = r - npv / dnpv
        if r_new <= -1:
            r_new = r / 2
        if abs(r_new - r) < tol:
            return round(r_new * 100, 2)
        r = r_new
    return round(r * 100, 2)


@dataclass
class InvestmentParams:
    """투자 시뮬레이션 파라미터."""
    ltv: float = 0.6               # 대출비율 (Loan to Value)
    loan_rate: float = 4.0         # 대출금리 (연 %)
    vacancy_months: float = 1.0    # 연간 예상 공실 (개월)
    mgmt_fee: int = 15             # 월 관리비 (만원)
    acquisition_tax_rate: float = 4.6  # 취득세율 (%)
    deposit_to_monthly: float = 0.04   # 보증금→월세 환산 비율 (연 4%)


@dataclass
class YieldAnalysis:
    """단일 권역 수익률 분석 결과."""
    region: str
    avg_price: int                  # 평균 매매가 (만원)
    avg_monthly_rent: int           # 평균 월세 (만원)
    avg_area: float                 # 평균 전용면적 (㎡)

    gross_yield: float              # 표면 수익률 (%)
    net_yield: float                # 실질 수익률 (%)
    leverage_yield: float           # 레버리지 수익률 (%)

    equity: int                     # 자기자본 (만원)
    loan_amount: int                # 대출금 (만원)
    monthly_interest: int           # 월 대출이자 (만원)
    monthly_net_income: int         # 월 순수익 (만원)
    annual_net_income: int          # 연 순수익 (만원)
    acquisition_tax: int            # 취득세 (만원)
    breakeven_years: float          # 취득세 회수 기간 (년)

    params: InvestmentParams
    is_sample: bool = False


def analyze_region(
    summary: RegionSummary,
    params: InvestmentParams | None = None,
) -> YieldAnalysis | None:
    """RegionSummary에서 투자 수익률 분석."""
    params = params or InvestmentParams()

    avg_price = summary.avg_trade_price
    avg_rent = summary.avg_monthly_rent
    avg_area = summary.avg_area

    if avg_price <= 0 or avg_rent <= 0:
        return None

    # 표면 수익률
    annual_gross_rent = avg_rent * 12
    gross_yield = (annual_gross_rent / avg_price) * 100

    # 실질 수익률 (관리비 + 공실 차감)
    effective_months = 12 - params.vacancy_months
    annual_net_rent = (avg_rent - params.mgmt_fee) * effective_months
    net_yield = (annual_net_rent / avg_price) * 100

    # 레버리지
    loan_amount = int(avg_price * params.ltv)
    equity = avg_price - loan_amount
    monthly_interest = int(loan_amount * params.loan_rate / 100 / 12)
    monthly_net = int((avg_rent - params.mgmt_fee) * effective_months / 12 - monthly_interest)
    annual_net = monthly_net * 12
    leverage_yield = (annual_net / equity * 100) if equity > 0 else 0

    # 취득세
    acquisition_tax = int(avg_price * params.acquisition_tax_rate / 100)

    # 손익분기점
    if annual_net > 0:
        breakeven_years = round(acquisition_tax / annual_net, 1)
    else:
        breakeven_years = float("inf")

    return YieldAnalysis(
        region=summary.region,
        avg_price=avg_price,
        avg_monthly_rent=avg_rent,
        avg_area=avg_area,
        gross_yield=round(gross_yield, 2),
        net_yield=round(net_yield, 2),
        leverage_yield=round(leverage_yield, 2),
        equity=equity,
        loan_amount=loan_amount,
        monthly_interest=monthly_interest,
        monthly_net_income=monthly_net,
        annual_net_income=annual_net,
        acquisition_tax=acquisition_tax,
        breakeven_years=breakeven_years,
        params=params,
        is_sample=summary.is_sample,
    )


def analyze_multi_region(
    summaries: list[RegionSummary],
    params: InvestmentParams | None = None,
) -> list[YieldAnalysis]:
    """여러 권역 일괄 분석."""
    results: list[YieldAnalysis] = []
    for s in summaries:
        a = analyze_region(s, params)
        if a is not None:
            results.append(a)
    return results


# ------------------------------------------------------------------
# 에이전트 컨텍스트 포매터
# ------------------------------------------------------------------

def _fmt_price(price: int) -> str:
    if price >= 10000:
        b = price // 10000
        r = price % 10000
        return f"{b}억 {r:,}만원" if r else f"{b}억"
    return f"{price:,}만원"


def format_analysis_for_agents(analyses: list[YieldAnalysis]) -> str:
    """수익률 분석 결과를 에이전트 주입용 텍스트로 변환."""
    if not analyses:
        return ""

    lines = ["=== 📊 투자 수익률 분석 ==="]
    sample_flag = any(a.is_sample for a in analyses)
    if sample_flag:
        lines.append("(⚠️ 샘플 데이터 기반 분석)")

    p = analyses[0].params
    lines.append(f"분석 조건: LTV {p.ltv*100:.0f}% | 대출금리 {p.loan_rate}% | "
                 f"공실 연 {p.vacancy_months}개월 | 관리비 월 {p.mgmt_fee}만원 | "
                 f"취득세 {p.acquisition_tax_rate}%")
    lines.append("")

    for a in analyses:
        lines.append(f"■ {a.region}")
        lines.append(f"  평균 매매가: {_fmt_price(a.avg_price)} (전용 {a.avg_area:.1f}㎡)")
        lines.append(f"  평균 월세: {a.avg_monthly_rent:,}만원")
        lines.append(f"  ─── 수익률 ───")
        lines.append(f"  표면 수익률: {a.gross_yield:.2f}%")
        lines.append(f"  실질 수익률: {a.net_yield:.2f}% (관리비·공실 차감)")
        lines.append(f"  레버리지 수익률: {a.leverage_yield:.2f}% (자기자본 {_fmt_price(a.equity)} 기준)")
        lines.append(f"  ─── 현금흐름 ───")
        lines.append(f"  대출: {_fmt_price(a.loan_amount)} → 월 이자 {a.monthly_interest:,}만원")
        lines.append(f"  월 순수익: {a.monthly_net_income:,}만원 | 연 순수익: {a.annual_net_income:,}만원")
        lines.append(f"  ─── 취득세 ───")
        lines.append(f"  취득세: {_fmt_price(a.acquisition_tax)}")
        if a.breakeven_years != float("inf"):
            lines.append(f"  취득세 회수 기간: {a.breakeven_years}년")
        else:
            lines.append(f"  취득세 회수 기간: ∞ (순수익 ≤ 0)")
        lines.append("")

    # 비교표
    if len(analyses) >= 2:
        lines.append("■ 권역 비교 요약")
        lines.append(f"  {'권역':<8} {'매매가':>10} {'월세':>8} {'표면':>6} {'실질':>6} {'레버리지':>8} {'월순수익':>8}")
        lines.append(f"  {'─'*8} {'─'*10} {'─'*8} {'─'*6} {'─'*6} {'─'*8} {'─'*8}")
        for a in analyses:
            lines.append(
                f"  {a.region:<8} {_fmt_price(a.avg_price):>10} "
                f"{a.avg_monthly_rent:>6,}만 "
                f"{a.gross_yield:>5.1f}% "
                f"{a.net_yield:>5.1f}% "
                f"{a.leverage_yield:>7.1f}% "
                f"{a.monthly_net_income:>6,}만원"
            )
        lines.append("")

        best_net = max(analyses, key=lambda x: x.net_yield)
        best_lev = max(analyses, key=lambda x: x.leverage_yield)
        best_cash = max(analyses, key=lambda x: x.monthly_net_income)
        lines.append(f"  실질 수익률 1위: {best_net.region} ({best_net.net_yield:.2f}%)")
        lines.append(f"  레버리지 수익률 1위: {best_lev.region} ({best_lev.leverage_yield:.2f}%)")
        lines.append(f"  월 순수익 1위: {best_cash.region} ({best_cash.monthly_net_income:,}만원)")
        lines.append("")

    lines.append("=== 수익률 분석 끝 ===")
    return "\n".join(lines)
