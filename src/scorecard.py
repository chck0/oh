"""투자 판단 스코어카드 — 정량 지표 기반 투자/대기/패스 추천.

수익률, 리스크, 현금흐름, 세금 등 복합 지표를 0~100점으로 환산하여
투자 적합성을 판단한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from yield_analyzer import YieldAnalysis
from cashflow import CashFlowTable
from monte_carlo import MonteCarloResult
from tax import TaxSummary

Verdict = Literal["투자 추천", "조건부 추천", "대기", "패스"]


@dataclass
class ScoreDetail:
    category: str
    score: float
    max_score: float
    note: str


@dataclass
class Scorecard:
    region: str
    details: list[ScoreDetail]
    total_score: float
    max_possible: float
    verdict: Verdict
    key_strengths: list[str]
    key_risks: list[str]


def _yield_score(analysis: YieldAnalysis) -> ScoreDetail:
    score = 0.0
    notes = []
    if analysis.gross_yield >= 5.0:
        score += 10
    elif analysis.gross_yield >= 4.0:
        score += 7
    elif analysis.gross_yield >= 3.0:
        score += 4
    else:
        score += 1

    if analysis.net_yield >= 3.5:
        score += 10
    elif analysis.net_yield >= 2.5:
        score += 6
    elif analysis.net_yield >= 1.5:
        score += 3
    else:
        score += 0

    if analysis.monthly_net_income > 50:
        score += 5
    elif analysis.monthly_net_income > 0:
        score += 3
    else:
        score += 0

    return ScoreDetail("수익률", round(score, 1), 25.0, f"표면 {analysis.gross_yield}% / 실질 {analysis.net_yield}%")


def _cashflow_score(cf: CashFlowTable | None) -> ScoreDetail:
    if cf is None:
        return ScoreDetail("현금흐름", 0, 25.0, "데이터 없음")
    score = 0.0
    if cf.irr is not None:
        if cf.irr >= 8:
            score += 10
        elif cf.irr >= 5:
            score += 7
        elif cf.irr >= 3:
            score += 5
        elif cf.irr >= 0:
            score += 2

    if cf.npv is not None and cf.npv > 0:
        score += 5
    elif cf.npv is not None:
        score += 1

    if cf.equity_multiple >= 1.5:
        score += 10
    elif cf.equity_multiple >= 1.2:
        score += 7
    elif cf.equity_multiple >= 1.0:
        score += 4
    else:
        score += 1

    irr_str = f"{cf.irr:.1f}%" if cf.irr else "N/A"
    return ScoreDetail("현금흐름", round(score, 1), 25.0, f"IRR {irr_str} / EM {cf.equity_multiple:.2f}x")


def _risk_score(mc: MonteCarloResult | None) -> ScoreDetail:
    if mc is None:
        return ScoreDetail("리스크", 0, 25.0, "데이터 없음")
    score = 0.0

    if mc.prob_loss <= 10:
        score += 10
    elif mc.prob_loss <= 25:
        score += 7
    elif mc.prob_loss <= 40:
        score += 4
    else:
        score += 1

    spread = mc.p95 - mc.p5
    if spread < 10:
        score += 5
    elif spread < 20:
        score += 3
    else:
        score += 1

    if mc.p50 >= 5:
        score += 10
    elif mc.p50 >= 3:
        score += 7
    elif mc.p50 >= 0:
        score += 4
    else:
        score += 1

    return ScoreDetail("리스크", round(score, 1), 25.0, f"손실확률 {mc.prob_loss:.1f}% / P50 IRR {mc.p50:.1f}%")


def _tax_score(tax: TaxSummary | None) -> ScoreDetail:
    if tax is None:
        return ScoreDetail("세금 효율", 0, 25.0, "데이터 없음")
    score = 0.0

    if tax.effective_tax_rate_pct <= 15:
        score += 10
    elif tax.effective_tax_rate_pct <= 30:
        score += 7
    elif tax.effective_tax_rate_pct <= 50:
        score += 4
    else:
        score += 1

    if tax.net_gain_after_tax > 5000:
        score += 10
    elif tax.net_gain_after_tax > 2000:
        score += 7
    elif tax.net_gain_after_tax > 0:
        score += 4
    else:
        score += 1

    if tax.acquisition.rate_pct <= 1.5:
        score += 5
    elif tax.acquisition.rate_pct <= 4:
        score += 3
    else:
        score += 1

    return ScoreDetail("세금 효율", round(score, 1), 25.0, f"실효세율 {tax.effective_tax_rate_pct}% / 세후 {tax.net_gain_after_tax:,.0f}만원")


def _determine_verdict(total: float) -> Verdict:
    if total >= 70:
        return "투자 추천"
    if total >= 55:
        return "조건부 추천"
    if total >= 40:
        return "대기"
    return "패스"


def _identify_strengths_risks(details: list[ScoreDetail]) -> tuple[list[str], list[str]]:
    strengths, risks = [], []
    for d in details:
        ratio = d.score / d.max_score if d.max_score > 0 else 0
        if ratio >= 0.7:
            strengths.append(f"{d.category}: {d.note}")
        elif ratio < 0.4:
            risks.append(f"{d.category}: {d.note}")
    return strengths, risks


def build_scorecard(
    analysis: YieldAnalysis,
    cf: CashFlowTable | None = None,
    mc: MonteCarloResult | None = None,
    tax: TaxSummary | None = None,
) -> Scorecard:
    details = [
        _yield_score(analysis),
        _cashflow_score(cf),
        _risk_score(mc),
        _tax_score(tax),
    ]
    total = sum(d.score for d in details)
    max_possible = sum(d.max_score for d in details)
    verdict = _determine_verdict(total)
    strengths, risks = _identify_strengths_risks(details)
    return Scorecard(
        region=analysis.region,
        details=details,
        total_score=round(total, 1),
        max_possible=max_possible,
        verdict=verdict,
        key_strengths=strengths,
        key_risks=risks,
    )


def build_multi_scorecard(
    analyses: list[YieldAnalysis],
    cf_tables: list[CashFlowTable] | None = None,
    mc_results: list[MonteCarloResult] | None = None,
    tax_summaries: list[TaxSummary] | None = None,
) -> list[Scorecard]:
    cards = []
    for i, a in enumerate(analyses):
        cf = cf_tables[i] if cf_tables and i < len(cf_tables) else None
        mc = mc_results[i] if mc_results and i < len(mc_results) else None
        tx = tax_summaries[i] if tax_summaries and i < len(tax_summaries) else None
        cards.append(build_scorecard(a, cf, mc, tx))
    return cards


def format_scorecard_for_agents(cards: list[Scorecard]) -> str:
    if not cards:
        return ""
    lines = ["═══ 투자 판단 스코어카드 ═══\n"]
    for c in cards:
        lines.append(f"■ {c.region} — {c.verdict} ({c.total_score}/{c.max_possible}점)")
        for d in c.details:
            bar_len = int(d.score / d.max_score * 10) if d.max_score > 0 else 0
            bar = "█" * bar_len + "░" * (10 - bar_len)
            lines.append(f"  {d.category:6s} [{bar}] {d.score:.0f}/{d.max_score:.0f}  {d.note}")
        if c.key_strengths:
            lines.append(f"  ✅ 강점: {'; '.join(c.key_strengths)}")
        if c.key_risks:
            lines.append(f"  ⚠️ 리스크: {'; '.join(c.key_risks)}")
        lines.append("")

    if len(cards) > 1:
        lines.append("▸ 종합 순위")
        ranked = sorted(cards, key=lambda c: c.total_score, reverse=True)
        for i, c in enumerate(ranked, 1):
            lines.append(f"  {i}위: {c.region} ({c.total_score}점) → {c.verdict}")
    return "\n".join(lines)
