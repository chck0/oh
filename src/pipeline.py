"""Shared data pipeline — 중복 제거용 공통 분석 파이프라인."""
from __future__ import annotations

from dataclasses import dataclass, field

from real_estate import RegionSummary, get_multi_region_data, format_for_agents
from yield_analyzer import (
    InvestmentParams, YieldAnalysis, analyze_multi_region, format_analysis_for_agents,
)
from scenario import format_full_scenario_for_agents
from cashflow import build_multi_cashflow, format_cashflow_for_agents
from monte_carlo import run_multi_monte_carlo, format_monte_carlo_for_agents
from tax import compute_multi_tax_summary, format_tax_for_agents
from scorecard import build_multi_scorecard, format_scorecard_for_agents
from portfolio import compare_portfolios, format_portfolio_for_agents


@dataclass
class PipelineResult:
    summaries: list[RegionSummary] = field(default_factory=list)
    analyses: list[YieldAnalysis] = field(default_factory=list)
    cf_tables: list = field(default_factory=list)
    mc_results: list = field(default_factory=list)
    tax_summaries: list = field(default_factory=list)
    scorecards: list = field(default_factory=list)
    portfolios: list = field(default_factory=list)

    market_text: str = ""
    yield_text: str = ""
    scenario_text: str = ""
    cashflow_text: str = ""
    mc_text: str = ""
    tax_text: str = ""
    score_text: str = ""
    port_text: str = ""

    @property
    def all_data_text(self) -> str:
        return "\n".join(filter(None, [
            self.market_text, self.yield_text, self.scenario_text,
            self.cashflow_text, self.mc_text,
            self.tax_text, self.score_text, self.port_text,
        ]))


def run_pipeline(
    regions: list[str],
    *,
    invest_params: InvestmentParams | None = None,
    property_type: str = "오피스텔",
    use_cashflow: bool = True,
    use_monte_carlo: bool = True,
    use_tax: bool = True,
    use_scorecard: bool = True,
    use_portfolio: bool = True,
) -> PipelineResult:
    r = PipelineResult()
    r.summaries = get_multi_region_data(regions, property_type=property_type)
    r.market_text = format_for_agents(r.summaries)

    r.analyses = analyze_multi_region(r.summaries, invest_params)
    r.yield_text = format_analysis_for_agents(r.analyses)
    r.scenario_text = format_full_scenario_for_agents(r.summaries, invest_params)

    if not r.analyses:
        return r

    if use_cashflow:
        r.cf_tables = build_multi_cashflow(r.analyses)
        r.cashflow_text = format_cashflow_for_agents(r.cf_tables)

    if use_monte_carlo:
        r.mc_results = run_multi_monte_carlo(r.analyses)
        r.mc_text = format_monte_carlo_for_agents(r.mc_results)

    if use_tax:
        r.tax_summaries = compute_multi_tax_summary(r.analyses)
        r.tax_text = format_tax_for_agents(r.tax_summaries)

    if use_scorecard:
        r.scorecards = build_multi_scorecard(
            r.analyses, r.cf_tables, r.mc_results, r.tax_summaries)
        r.score_text = format_scorecard_for_agents(r.scorecards)

    if use_portfolio and len(r.analyses) >= 2:
        r.portfolios = compare_portfolios(r.analyses, r.cf_tables, r.mc_results)
        r.port_text = format_portfolio_for_agents(r.portfolios)

    return r
