"""10년 현금흐름 프로젝션 — 연도별 임대수익·비용·자산가치 추이.

임대료 상승률, 비용 인플레이션, 자산 가치 상승을 반영한
장기 투자 수익률(IRR/NPV) 분석.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from yield_analyzer import YieldAnalysis, InvestmentParams, compute_irr, compute_npv


@dataclass
class CashFlowParams:
    holding_years: int = 10
    rental_growth: float = 2.0       # 연간 임대료 상승률 (%)
    expense_inflation: float = 3.0   # 연간 비용 상승률 (%)
    appreciation: float = 2.0        # 연간 자산가치 상승률 (%)
    discount_rate: float = 3.5       # NPV 할인율 (%)
    selling_cost_pct: float = 2.0    # 매각 비용 (중개+세금, %)


@dataclass
class YearRow:
    year: int
    gross_rent: int          # 연간 총 임대료 (만원)
    expenses: int            # 연간 비용 (관리비+공실) (만원)
    loan_payment: int        # 연간 대출이자 (만원)
    net_income: int          # 연간 순수익 (만원)
    cumulative: int          # 누적 순수익 (만원)
    property_value: int      # 연말 자산가치 (만원)


@dataclass
class CashFlowTable:
    region: str
    rows: list[YearRow] = field(default_factory=list)
    initial_outflow: int = 0    # 초기 투자금 (자기자본 + 취득세)
    terminal_value: int = 0     # 매각 시 순수령액
    irr: float = 0.0
    npv: float = 0.0
    equity_multiple: float = 0.0
    params: CashFlowParams = field(default_factory=CashFlowParams)


def build_cashflow_table(
    analysis: YieldAnalysis,
    params: CashFlowParams | None = None,
) -> CashFlowTable:
    params = params or CashFlowParams()
    p = analysis.params

    initial = analysis.equity + analysis.acquisition_tax
    monthly_rent = analysis.avg_monthly_rent
    monthly_mgmt = p.mgmt_fee
    vacancy = p.vacancy_months
    annual_interest = analysis.monthly_interest * 12
    property_value = analysis.avg_price

    rows: list[YearRow] = []
    cumulative = 0
    cf_vector: list[float] = [float(-initial)]

    for yr in range(1, params.holding_years + 1):
        if yr > 1:
            monthly_rent = int(monthly_rent * (1 + params.rental_growth / 100))
            monthly_mgmt = int(monthly_mgmt * (1 + params.expense_inflation / 100))

        effective_months = 12 - vacancy
        gross = monthly_rent * 12
        expenses = int(monthly_mgmt * 12 + monthly_rent * vacancy)
        net = int((monthly_rent - monthly_mgmt) * effective_months - annual_interest)
        cumulative += net

        property_value = int(property_value * (1 + params.appreciation / 100))

        rows.append(YearRow(
            year=yr,
            gross_rent=gross,
            expenses=expenses,
            loan_payment=annual_interest,
            net_income=net,
            cumulative=cumulative,
            property_value=property_value,
        ))

        if yr < params.holding_years:
            cf_vector.append(float(net))
        else:
            sell_net = int(property_value * (1 - params.selling_cost_pct / 100))
            terminal = sell_net - analysis.loan_amount
            cf_vector.append(float(net + terminal))

    terminal_value = int(
        property_value * (1 - params.selling_cost_pct / 100)
    ) - analysis.loan_amount

    irr = compute_irr(cf_vector)
    npv = round(compute_npv(cf_vector, params.discount_rate / 100), 0)
    eq_mul = round((cumulative + terminal_value) / initial, 2) if initial > 0 else 0

    return CashFlowTable(
        region=analysis.region,
        rows=rows,
        initial_outflow=initial,
        terminal_value=terminal_value,
        irr=irr,
        npv=npv,
        equity_multiple=eq_mul,
        params=params,
    )


def build_multi_cashflow(
    analyses: list[YieldAnalysis],
    params: CashFlowParams | None = None,
) -> list[CashFlowTable]:
    return [build_cashflow_table(a, params) for a in analyses]


def format_cashflow_for_agents(tables: list[CashFlowTable]) -> str:
    if not tables:
        return ""
    lines = ["=== 💰 10년 현금흐름 프로젝션 ===", ""]
    for t in tables:
        lines.append(f"■ {t.region} ({t.params.holding_years}년 보유)")
        lines.append(f"  초기 투자: {_f(t.initial_outflow)} (자기자본+취득세)")
        lines.append(f"  임대료 상승: 연 {t.params.rental_growth}% | "
                     f"비용 상승: 연 {t.params.expense_inflation}% | "
                     f"자산 상승: 연 {t.params.appreciation}%")
        lines.append(f"  {'연도':>4} {'총임대료':>8} {'비용':>8} {'이자':>8} {'순수익':>8} {'누적':>10} {'자산가치':>12}")
        lines.append(f"  {'─'*4} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*10} {'─'*12}")
        for r in t.rows:
            lines.append(
                f"  {r.year:>4} {r.gross_rent:>7,}만 {r.expenses:>7,}만 "
                f"{r.loan_payment:>7,}만 {r.net_income:>7,}만 "
                f"{r.cumulative:>9,}만 {_f(r.property_value):>12}"
            )
        lines.append(f"  ─── 매각 시점 ───")
        lines.append(f"  매각 순수령: {_f(t.terminal_value)}")
        lines.append(f"  IRR: {t.irr:.1f}% | NPV(@{t.params.discount_rate}%): {_f(int(t.npv))} | "
                     f"배수: {t.equity_multiple:.2f}x")
        lines.append("")

    if len(tables) >= 2:
        lines.append("■ IRR 비교")
        for t in sorted(tables, key=lambda x: x.irr, reverse=True):
            lines.append(f"  {t.region}: IRR {t.irr:.1f}% | NPV {_f(int(t.npv))} | {t.equity_multiple:.2f}x")
        lines.append("")

    lines.append("=== 현금흐름 프로젝션 끝 ===")
    return "\n".join(lines)


def _f(price: int) -> str:
    if abs(price) >= 10000:
        b = price // 10000
        r = abs(price) % 10000
        return f"{b}억 {r:,}만원" if r else f"{b}억"
    return f"{price:,}만원"
