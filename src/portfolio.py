"""포트폴리오 분석 — 다중 매물 조합의 수익/리스크 트레이드오프.

여러 권역의 매물을 조합했을 때 포트폴리오 수준의
기대수익률, 리스크(변동성), 분산효과를 분석한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from yield_analyzer import YieldAnalysis
from cashflow import CashFlowTable
from monte_carlo import MonteCarloResult


@dataclass
class PortfolioItem:
    region: str
    weight: float
    expected_irr: float
    irr_std: float
    monthly_income: float


@dataclass
class PortfolioResult:
    items: list[PortfolioItem]
    portfolio_irr: float
    portfolio_std: float
    total_monthly_income: float
    total_investment: float
    diversification_benefit: float
    correlation_note: str


def build_portfolio(
    analyses: list[YieldAnalysis],
    cf_tables: list[CashFlowTable] | None = None,
    mc_results: list[MonteCarloResult] | None = None,
    weights: list[float] | None = None,
) -> PortfolioResult:
    n = len(analyses)
    if weights is None:
        weights = [1.0 / n] * n

    items = []
    total_inv = sum(a.equity for a in analyses)

    for i, a in enumerate(analyses):
        w = a.equity / total_inv if total_inv > 0 else weights[i]
        irr = mc_results[i].irr_mean if mc_results and i < len(mc_results) else 0.0
        std = mc_results[i].irr_std if mc_results and i < len(mc_results) else 0.0
        income = a.monthly_net_income
        items.append(PortfolioItem(
            region=a.region, weight=round(w, 3),
            expected_irr=round(irr, 2), irr_std=round(std, 2),
            monthly_income=round(income, 1),
        ))

    port_irr = sum(it.weight * it.expected_irr for it in items)

    weighted_var_sum = sum(it.weight ** 2 * it.irr_std ** 2 for it in items)
    simple_std = (weighted_var_sum ** 0.5) if weighted_var_sum > 0 else 0

    naive_std = sum(it.weight * it.irr_std for it in items)
    div_benefit = round(naive_std - simple_std, 2) if naive_std > simple_std else 0.0

    if n <= 1:
        corr_note = "단일 매물 — 분산효과 없음"
    elif div_benefit > 1.0:
        corr_note = "강한 분산효과 — 리스크 크게 감소"
    elif div_benefit > 0:
        corr_note = "분산효과 존재 — 포트폴리오 리스크 감소"
    else:
        corr_note = "분산효과 미미 — 유사한 리스크 프로파일"

    total_income = sum(a.monthly_net_income for a in analyses)

    return PortfolioResult(
        items=items,
        portfolio_irr=round(port_irr, 2),
        portfolio_std=round(simple_std, 2),
        total_monthly_income=round(total_income, 1),
        total_investment=round(total_inv, 1),
        diversification_benefit=div_benefit,
        correlation_note=corr_note,
    )


@dataclass
class PortfolioComparison:
    combo_label: str
    result: PortfolioResult


def compare_portfolios(
    analyses: list[YieldAnalysis],
    cf_tables: list[CashFlowTable] | None = None,
    mc_results: list[MonteCarloResult] | None = None,
) -> list[PortfolioComparison]:
    comparisons = []
    n = len(analyses)

    for i in range(n):
        single = build_portfolio(
            [analyses[i]],
            [cf_tables[i]] if cf_tables else None,
            [mc_results[i]] if mc_results else None,
        )
        comparisons.append(PortfolioComparison(
            combo_label=analyses[i].region, result=single,
        ))

    if n >= 2:
        for combo in combinations(range(n), 2):
            sub_a = [analyses[j] for j in combo]
            sub_cf = [cf_tables[j] for j in combo] if cf_tables else None
            sub_mc = [mc_results[j] for j in combo] if mc_results else None
            result = build_portfolio(sub_a, sub_cf, sub_mc)
            label = " + ".join(analyses[j].region for j in combo)
            comparisons.append(PortfolioComparison(combo_label=label, result=result))

    if n >= 3:
        result = build_portfolio(analyses, cf_tables, mc_results)
        label = " + ".join(a.region for a in analyses)
        comparisons.append(PortfolioComparison(combo_label=label, result=result))

    return comparisons


def format_portfolio_for_agents(comparisons: list[PortfolioComparison]) -> str:
    if not comparisons:
        return ""
    lines = ["═══ 포트폴리오 분석 ═══\n"]

    for comp in comparisons:
        r = comp.result
        n_items = len(r.items)
        lines.append(f"▸ {comp.combo_label} {'(단일)' if n_items == 1 else f'({n_items}개 조합)'}")
        lines.append(f"  기대 IRR: {r.portfolio_irr:.1f}%  |  변동성: {r.portfolio_std:.1f}%")
        lines.append(f"  총 투자금: {r.total_investment:,.0f}만원  |  월 순수익 합계: {r.total_monthly_income:,.0f}만원")
        if n_items > 1:
            lines.append(f"  분산효과: {r.diversification_benefit:.1f}%p ({r.correlation_note})")
            for it in r.items:
                lines.append(f"    - {it.region}: 비중 {it.weight:.0%}, IRR {it.expected_irr:.1f}%±{it.irr_std:.1f}%")
        lines.append("")

    best = max(comparisons, key=lambda c: c.result.portfolio_irr)
    safest = min(comparisons, key=lambda c: c.result.portfolio_std)
    lines.append("▸ 추천 조합")
    lines.append(f"  수익 최적: {best.combo_label} (IRR {best.result.portfolio_irr:.1f}%)")
    lines.append(f"  안정 최적: {safest.combo_label} (변동성 {safest.result.portfolio_std:.1f}%)")

    return "\n".join(lines)
