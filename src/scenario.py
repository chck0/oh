"""시나리오 시뮬레이터 — What-If 분석.

금리/공실/매매가 등 변수를 변동시켜 투자 수익률이 어떻게 바뀌는지
시뮬레이션하고, 에이전트(특히 CSO)가 리스크를 분석할 수 있는 데이터를 제공한다.

시나리오 종류:
1. 금리 민감도: 금리 ±0.5%p 단위로 변동 시 레버리지 수익률/월 순수익 변화
2. 공실 민감도: 공실 0~3개월 변동 시 실질 수익률/월 순수익 변화
3. 매매가 민감도: 매매가 ±10% 변동 시 수익률 변화 (시세 하락/상승 시나리오)
4. 복합 스트레스 테스트: 최악/기본/최선 3개 시나리오 일괄 비교
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from real_estate import RegionSummary
from yield_analyzer import (
    InvestmentParams,
    YieldAnalysis,
    analyze_region,
    _fmt_price,
)


@dataclass
class ScenarioResult:
    """하나의 시나리오 포인트 결과."""
    label: str
    params: InvestmentParams
    analysis: YieldAnalysis


@dataclass
class SensitivityTable:
    """하나의 변수에 대한 민감도 분석 결과."""
    variable_name: str
    variable_unit: str
    region: str
    base_value: float
    results: list[ScenarioResult]


@dataclass
class StressTest:
    """최악/기본/최선 3-시나리오 스트레스 테스트."""
    region: str
    worst: ScenarioResult
    base: ScenarioResult
    best: ScenarioResult


# ------------------------------------------------------------------
# 민감도 분석
# ------------------------------------------------------------------


def rate_sensitivity(
    summary: RegionSummary,
    base_params: InvestmentParams | None = None,
    steps: list[float] | None = None,
) -> SensitivityTable | None:
    """대출금리 변동 민감도 분석."""
    base = base_params or InvestmentParams()
    steps = steps or [-1.0, -0.5, 0, 0.5, 1.0, 1.5]
    results: list[ScenarioResult] = []

    for delta in steps:
        rate = base.loan_rate + delta
        if rate < 0:
            continue
        p = replace(base, loan_rate=round(rate, 1))
        a = analyze_region(summary, p)
        if a is None:
            continue
        sign = "+" if delta > 0 else ""
        label = f"금리 {rate:.1f}% ({sign}{delta:.1f}%p)" if delta != 0 else f"금리 {rate:.1f}% (현재)"
        results.append(ScenarioResult(label=label, params=p, analysis=a))

    if not results:
        return None
    return SensitivityTable(
        variable_name="대출금리",
        variable_unit="%",
        region=summary.region,
        base_value=base.loan_rate,
        results=results,
    )


def vacancy_sensitivity(
    summary: RegionSummary,
    base_params: InvestmentParams | None = None,
    steps: list[float] | None = None,
) -> SensitivityTable | None:
    """공실 변동 민감도 분석."""
    base = base_params or InvestmentParams()
    steps = steps or [0, 0.5, 1.0, 1.5, 2.0, 3.0]
    results: list[ScenarioResult] = []

    for months in steps:
        p = replace(base, vacancy_months=months)
        a = analyze_region(summary, p)
        if a is None:
            continue
        if months == base.vacancy_months:
            label = f"공실 {months}개월 (현재)"
        else:
            label = f"공실 {months}개월"
        results.append(ScenarioResult(label=label, params=p, analysis=a))

    if not results:
        return None
    return SensitivityTable(
        variable_name="연간 공실",
        variable_unit="개월",
        region=summary.region,
        base_value=base.vacancy_months,
        results=results,
    )


def price_sensitivity(
    summary: RegionSummary,
    base_params: InvestmentParams | None = None,
    pct_changes: list[float] | None = None,
) -> SensitivityTable | None:
    """매매가 변동 민감도 분석 (월세 고정, 매매가만 변동)."""
    base = base_params or InvestmentParams()
    pct_changes = pct_changes or [-20, -10, -5, 0, 5, 10, 20]
    results: list[ScenarioResult] = []

    orig_price = summary.avg_trade_price
    if orig_price <= 0:
        return None

    for pct in pct_changes:
        factor = 1 + pct / 100
        modified = _modify_prices(summary, factor)
        a = analyze_region(modified, base)
        if a is None:
            continue
        if pct == 0:
            label = f"매매가 현재 ({_fmt_price(orig_price)})"
        else:
            sign = "+" if pct > 0 else ""
            new_price = int(orig_price * factor)
            label = f"매매가 {sign}{pct}% ({_fmt_price(new_price)})"
        results.append(ScenarioResult(label=label, params=base, analysis=a))

    if not results:
        return None
    return SensitivityTable(
        variable_name="매매가 변동",
        variable_unit="%",
        region=summary.region,
        base_value=0,
        results=results,
    )


# ------------------------------------------------------------------
# 스트레스 테스트
# ------------------------------------------------------------------


def stress_test(
    summary: RegionSummary,
    base_params: InvestmentParams | None = None,
) -> StressTest | None:
    """최악/기본/최선 3-시나리오 스트레스 테스트."""
    base = base_params or InvestmentParams()

    worst_params = replace(
        base,
        loan_rate=base.loan_rate + 1.5,
        vacancy_months=min(base.vacancy_months + 2.0, 4.0),
        mgmt_fee=base.mgmt_fee + 5,
    )
    worst_summary = _modify_prices(summary, 0.9)

    best_params = replace(
        base,
        loan_rate=max(base.loan_rate - 1.0, 1.0),
        vacancy_months=max(base.vacancy_months - 0.5, 0),
        mgmt_fee=max(base.mgmt_fee - 5, 5),
    )
    best_summary = _modify_prices(summary, 1.1)

    base_a = analyze_region(summary, base)
    worst_a = analyze_region(worst_summary, worst_params)
    best_a = analyze_region(summary, best_params)

    if not all([base_a, worst_a, best_a]):
        return None

    return StressTest(
        region=summary.region,
        worst=ScenarioResult(label="최악 시나리오", params=worst_params, analysis=worst_a),
        base=ScenarioResult(label="기본 시나리오", params=base, analysis=base_a),
        best=ScenarioResult(label="최선 시나리오", params=best_params, analysis=best_a),
    )


# ------------------------------------------------------------------
# 에이전트 컨텍스트 포매터
# ------------------------------------------------------------------


def format_sensitivity_for_agents(table: SensitivityTable) -> str:
    """민감도 분석 결과를 텍스트로 변환."""
    lines = [f"▸ {table.region} — {table.variable_name} 민감도 분석"]
    lines.append(f"  {'시나리오':<25} {'실질':>6} {'레버리지':>8} {'월순수익':>8}")
    lines.append(f"  {'─'*25} {'─'*6} {'─'*8} {'─'*8}")
    for r in table.results:
        a = r.analysis
        marker = " ◀" if "현재" in r.label else ""
        lines.append(
            f"  {r.label:<25} {a.net_yield:>5.1f}% {a.leverage_yield:>7.1f}% "
            f"{a.monthly_net_income:>6,}만원{marker}"
        )
    return "\n".join(lines)


def format_stress_for_agents(st: StressTest) -> str:
    """스트레스 테스트 결과를 텍스트로 변환."""
    lines = [f"▸ {st.region} — 스트레스 테스트 (최악 / 기본 / 최선)"]

    def _row(r: ScenarioResult) -> str:
        a = r.analysis
        p = r.params
        return (
            f"  {r.label:<14} "
            f"금리 {p.loan_rate:.1f}% | 공실 {p.vacancy_months}개월 | "
            f"실질 {a.net_yield:.1f}% | 레버리지 {a.leverage_yield:.1f}% | "
            f"월순수익 {a.monthly_net_income:,}만원"
        )

    lines.append(_row(st.worst))
    lines.append(_row(st.base))
    lines.append(_row(st.best))

    spread = st.best.analysis.monthly_net_income - st.worst.analysis.monthly_net_income
    lines.append(f"  → 최악~최선 월순수익 변동폭: {spread:,}만원")
    return "\n".join(lines)


def format_full_scenario_for_agents(
    summaries: list[RegionSummary],
    base_params: InvestmentParams | None = None,
) -> str:
    """여러 권역의 시나리오 분석을 하나의 텍스트 블록으로 합침."""
    base = base_params or InvestmentParams()
    blocks: list[str] = ["=== 🔮 시나리오 시뮬레이션 ==="]
    any_sample = any(s.is_sample for s in summaries)
    if any_sample:
        blocks.append("(⚠️ 샘플 데이터 기반 시뮬레이션)")
    blocks.append("")

    for summary in summaries:
        rt = rate_sensitivity(summary, base)
        if rt:
            blocks.append(format_sensitivity_for_agents(rt))
            blocks.append("")

        vt = vacancy_sensitivity(summary, base)
        if vt:
            blocks.append(format_sensitivity_for_agents(vt))
            blocks.append("")

        pt = price_sensitivity(summary, base)
        if pt:
            blocks.append(format_sensitivity_for_agents(pt))
            blocks.append("")

        st_result = stress_test(summary, base)
        if st_result:
            blocks.append(format_stress_for_agents(st_result))
            blocks.append("")

    blocks.append("=== 시나리오 시뮬레이션 끝 ===")
    return "\n".join(blocks)


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------


def _modify_prices(summary: RegionSummary, factor: float) -> RegionSummary:
    """매매가를 factor 배로 조정한 복사본 생성 (월세는 유지)."""
    from real_estate import TradeRecord
    new_trades = [
        replace(r, price=int(r.price * factor))
        for r in summary.trade_records
    ]
    return replace(summary, trade_records=new_trades)
