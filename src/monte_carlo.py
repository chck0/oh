"""Monte Carlo 시뮬레이션 — 확률 기반 투자 리스크 분석.

금리·공실·임대료상승·자산가치 변동을 상관관계 포함하여
N회 시뮬레이션하고, IRR/NPV 분포 + 손실 확률을 산출한다.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from cashflow import CashFlowParams, CashFlowTable, build_cashflow_table
from yield_analyzer import YieldAnalysis


@dataclass
class MonteCarloParams:
    n_simulations: int = 3000
    rent_growth: tuple[float, float] = (2.0, 1.5)       # (mean%, std%)
    vacancy_months: tuple[float, float] = (1.0, 0.8)    # (mean, std)
    rate_change: tuple[float, float] = (0.0, 0.5)       # (mean%p, std%p)
    appreciation: tuple[float, float] = (2.0, 3.0)      # (mean%, std%)
    holding_years: int = 10

    @property
    def correlation_matrix(self) -> list[list[float]]:
        return [
            [1.0,  -0.2, -0.1,  0.3],   # rent_growth
            [-0.2,  1.0,  0.3, -0.2],   # vacancy
            [-0.1,  0.3,  1.0, -0.3],   # rate
            [0.3,  -0.2, -0.3,  1.0],   # appreciation
        ]


@dataclass
class MonteCarloResult:
    region: str
    irr_list: list[float] = field(default_factory=list)
    npv_list: list[float] = field(default_factory=list)
    p5: float = 0.0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p95: float = 0.0
    irr_mean: float = 0.0
    irr_std: float = 0.0
    prob_loss: float = 0.0
    n_simulations: int = 0


def run_monte_carlo(
    analysis: YieldAnalysis,
    mc_params: MonteCarloParams | None = None,
    cf_base: CashFlowParams | None = None,
) -> MonteCarloResult:
    mc = mc_params or MonteCarloParams()
    cf_base = cf_base or CashFlowParams(holding_years=mc.holding_years)

    L = _cholesky(mc.correlation_matrix)
    irr_list: list[float] = []
    npv_list: list[float] = []

    for _ in range(mc.n_simulations):
        z = [random.gauss(0, 1) for _ in range(4)]
        correlated = _mat_vec(L, z)

        rg = mc.rent_growth[0] + mc.rent_growth[1] * correlated[0]
        vm = max(0, mc.vacancy_months[0] + mc.vacancy_months[1] * correlated[1])
        rc = mc.rate_change[0] + mc.rate_change[1] * correlated[2]
        ap = mc.appreciation[0] + mc.appreciation[1] * correlated[3]

        sim_params = CashFlowParams(
            holding_years=cf_base.holding_years,
            rental_growth=rg,
            expense_inflation=cf_base.expense_inflation,
            appreciation=ap,
            discount_rate=cf_base.discount_rate,
            selling_cost_pct=cf_base.selling_cost_pct,
        )

        from dataclasses import replace
        sim_invest = replace(
            analysis.params,
            vacancy_months=vm,
            loan_rate=max(0.5, analysis.params.loan_rate + rc),
        )
        sim_analysis = replace(analysis, params=sim_invest)
        # recalculate monthly interest with new rate
        loan = sim_analysis.loan_amount
        new_interest = int(loan * sim_invest.loan_rate / 100 / 12)
        sim_analysis = replace(sim_analysis, monthly_interest=new_interest)

        try:
            table = build_cashflow_table(sim_analysis, sim_params)
            irr_list.append(table.irr)
            npv_list.append(table.npv)
        except Exception:
            continue

    if not irr_list:
        return MonteCarloResult(region=analysis.region, n_simulations=0)

    irr_sorted = sorted(irr_list)
    n = len(irr_sorted)
    mean_irr = sum(irr_sorted) / n
    var = sum((x - mean_irr) ** 2 for x in irr_sorted) / n
    std_irr = math.sqrt(var)

    return MonteCarloResult(
        region=analysis.region,
        irr_list=irr_list,
        npv_list=npv_list,
        p5=irr_sorted[int(n * 0.05)],
        p25=irr_sorted[int(n * 0.25)],
        p50=irr_sorted[int(n * 0.50)],
        p75=irr_sorted[int(n * 0.75)],
        p95=irr_sorted[min(int(n * 0.95), n - 1)],
        irr_mean=round(mean_irr, 2),
        irr_std=round(std_irr, 2),
        prob_loss=round(sum(1 for x in npv_list if x < 0) / n * 100, 1),
        n_simulations=n,
    )


def run_multi_monte_carlo(
    analyses: list[YieldAnalysis],
    mc_params: MonteCarloParams | None = None,
) -> list[MonteCarloResult]:
    return [run_monte_carlo(a, mc_params) for a in analyses]


def format_monte_carlo_for_agents(results: list[MonteCarloResult]) -> str:
    if not results:
        return ""
    lines = ["=== 🎲 Monte Carlo 시뮬레이션 ===", ""]
    for r in results:
        if r.n_simulations == 0:
            continue
        lines.append(f"■ {r.region} ({r.n_simulations:,}회 시뮬레이션)")
        lines.append(f"  IRR 분포:")
        lines.append(f"    평균: {r.irr_mean:.1f}% (표준편차: {r.irr_std:.1f}%p)")
        lines.append(f"    P5(최악): {r.p5:.1f}% | P25: {r.p25:.1f}% | "
                     f"P50(중앙): {r.p50:.1f}% | P75: {r.p75:.1f}% | P95(최선): {r.p95:.1f}%")
        lines.append(f"  손실 확률 (NPV<0): {r.prob_loss:.1f}%")
        if r.prob_loss > 30:
            lines.append(f"  ⚠️ 주의: 손실 확률이 30%를 초과합니다")
        lines.append("")

    if len(results) >= 2:
        valid = [r for r in results if r.n_simulations > 0]
        if valid:
            lines.append("■ 리스크 비교")
            for r in sorted(valid, key=lambda x: x.prob_loss):
                lines.append(f"  {r.region}: 손실확률 {r.prob_loss:.1f}% | "
                             f"IRR중앙 {r.p50:.1f}% | 변동폭(P5~P95) {r.p95-r.p5:.1f}%p")
            lines.append("")

    lines.append("=== Monte Carlo 끝 ===")
    return "\n".join(lines)


def _cholesky(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                val = matrix[i][i] - s
                L[i][j] = math.sqrt(max(val, 0))
            else:
                L[i][j] = (matrix[i][j] - s) / L[j][j] if L[j][j] != 0 else 0
    return L


def _mat_vec(L: list[list[float]], v: list[float]) -> list[float]:
    return [sum(L[i][j] * v[j] for j in range(len(v))) for i in range(len(L))]
