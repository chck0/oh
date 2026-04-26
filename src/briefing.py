"""CEO 사전 브리핑 보고서 생성 — 회의 전 핵심 데이터 요약."""
from __future__ import annotations

import math
from datetime import date

from pipeline import PipelineResult


def _safe_pct(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        return "—"
    return f"{value:.1f}%"


def generate_ceo_briefing(result: PipelineResult, topic: str = "") -> str:
    if not result.summaries:
        return ""

    lines: list[str] = []
    today = date.today().strftime("%Y-%m-%d")
    regions_str = ", ".join(s.region for s in result.summaries)
    sample_flag = any(s.is_sample for s in result.summaries)

    lines.append(f"# 📋 CEO 사전 브리핑 보고서")
    lines.append(f"**작성일**: {today}  ")
    if topic:
        lines.append(f"**안건**: {topic}  ")
    lines.append(f"**분석 대상**: {regions_str}  ")
    if sample_flag:
        lines.append("**⚠️ 데이터**: 샘플 데이터 기반 (실제 API 연동 시 실거래가로 대체)  ")
    lines.append("")

    lines.append("---")
    lines.append("")

    # ── 1. Executive Summary ──
    lines.append("## 1. 핵심 요약 (Executive Summary)")
    lines.append("")
    if result.scorecards:
        best = max(result.scorecards, key=lambda c: c.total_score)
        lines.append(
            f"- **최우수 투자처**: {best.region} "
            f"({best.total_score:.0f}/{best.max_possible:.0f}점, {best.verdict})"
        )
    if result.analyses:
        top_yield = max(result.analyses, key=lambda a: a.net_yield)
        lines.append(
            f"- **최고 순수익률**: {top_yield.region} "
            f"(순수익률 {top_yield.net_yield:.2f}%, "
            f"레버리지 {top_yield.leverage_yield:.2f}%)"
        )
    if result.mc_results:
        safest = min(result.mc_results, key=lambda m: m.prob_loss)
        lines.append(
            f"- **최저 손실확률**: {safest.region} "
            f"(손실확률 {safest.prob_loss:.1f}%)"
        )
    lines.append("")

    # ── 2. 시장 현황 ──
    lines.append("## 2. 시장 현황 (실거래 데이터)")
    lines.append("")
    lines.append("| 지역 | 평균 매매가 | 평균 월세 | 평균 면적 | 거래 건수 |")
    lines.append("|------|-----------|----------|----------|----------|")
    for s in result.summaries:
        price = f"{s.avg_trade_price:,}만원" if s.avg_trade_price else "—"
        rent = f"{s.avg_monthly_rent:,}만원" if s.avg_monthly_rent else "—"
        area = f"{s.avg_area:.1f}㎡" if s.avg_area else "—"
        count = len(s.trade_records)
        lines.append(f"| {s.region} | {price} | {rent} | {area} | {count}건 |")
    lines.append("")

    # ── 3. 수익률 분석 ──
    if result.analyses:
        lines.append("## 3. 수익률 분석")
        lines.append("")
        lines.append("| 지역 | 표면수익률 | 순수익률 | 레버리지 | 자기자본 | 월 순수입 | 손익분기 |")
        lines.append("|------|----------|---------|---------|---------|---------|---------|")
        for a in result.analyses:
            lines.append(
                f"| {a.region} "
                f"| {a.gross_yield:.2f}% "
                f"| {a.net_yield:.2f}% "
                f"| {a.leverage_yield:.2f}% "
                f"| {a.equity:,}만원 "
                f"| {a.monthly_net_income:,}만원 "
                f"| {a.breakeven_years:.1f}년 |"
            )
        lines.append("")

    # ── 4. 리스크 시뮬레이션 ──
    if result.mc_results:
        lines.append("## 4. 리스크 시뮬레이션 (Monte Carlo)")
        lines.append("")
        lines.append("| 지역 | IRR 중앙값 | IRR 평균 | 변동성 | 손실확률 | 낙관(P95) | 비관(P5) |")
        lines.append("|------|----------|---------|-------|---------|----------|---------|")
        for m in result.mc_results:
            lines.append(
                f"| {m.region} "
                f"| {_safe_pct(m.p50)} "
                f"| {_safe_pct(m.irr_mean)} "
                f"| {_safe_pct(m.irr_std)} "
                f"| {_safe_pct(m.prob_loss)} "
                f"| {_safe_pct(m.p95)} "
                f"| {_safe_pct(m.p5)} |"
            )
        lines.append("")

    # ── 5. 현금흐름 요약 ──
    if result.cf_tables:
        lines.append("## 5. 10년 현금흐름 전망")
        lines.append("")
        lines.append("| 지역 | IRR | NPV | 자본배수 | 초기 투자 |")
        lines.append("|------|-----|-----|---------|---------|")
        for cf in result.cf_tables:
            lines.append(
                f"| {cf.region} "
                f"| {cf.irr:.1f}% "
                f"| {cf.npv:,.0f}만원 "
                f"| {cf.equity_multiple:.2f}x "
                f"| {cf.initial_outflow:,}만원 |"
            )
        lines.append("")

    # ── 6. 세금 영향 ──
    if result.tax_summaries:
        lines.append("## 6. 세금 시뮬레이션")
        lines.append("")
        lines.append("| 지역 | 취득세 | 보유세(연) | 양도세 | 총 세금 | 실효세율 | 세후 순이익 |")
        lines.append("|------|-------|----------|-------|--------|---------|-----------|")
        for t in result.tax_summaries:
            lines.append(
                f"| {t.region} "
                f"| {t.acquisition.amount:,.0f}만원 "
                f"| {t.holding.total_annual:,.0f}만원 "
                f"| {t.capital_gains.tax_amount:,.0f}만원 "
                f"| {t.total_tax:,.0f}만원 "
                f"| {t.effective_tax_rate_pct:.1f}% "
                f"| {t.net_gain_after_tax:,.0f}만원 |"
            )
        lines.append("")

    # ── 7. 투자 스코어카드 ──
    if result.scorecards:
        lines.append("## 7. 투자 스코어카드")
        lines.append("")
        for card in result.scorecards:
            lines.append(
                f"### {card.region}: {card.verdict} "
                f"({card.total_score:.0f}/{card.max_possible:.0f}점)"
            )
            if card.key_strengths:
                lines.append(f"- **강점**: {'; '.join(card.key_strengths)}")
            if card.key_risks:
                lines.append(f"- **리스크**: {'; '.join(card.key_risks)}")
            lines.append("")

    # ── 8. 포트폴리오 추천 ──
    if result.portfolios:
        lines.append("## 8. 포트폴리오 추천")
        lines.append("")
        valid = [c for c in result.portfolios
                 if math.isfinite(c.result.portfolio_irr)]
        if valid:
            best_irr = max(valid, key=lambda c: c.result.portfolio_irr)
            lines.append(
                f"- **수익 극대화**: {best_irr.combo_label} "
                f"(IRR {best_irr.result.portfolio_irr:.1f}%, "
                f"월 {best_irr.result.total_monthly_income:,}만원)"
            )
        valid_std = [c for c in result.portfolios
                     if math.isfinite(c.result.portfolio_std)]
        if valid_std:
            safest = min(valid_std, key=lambda c: c.result.portfolio_std)
            lines.append(
                f"- **안정성 우선**: {safest.combo_label} "
                f"(변동성 {safest.result.portfolio_std:.1f}%, "
                f"월 {safest.result.total_monthly_income:,}만원)"
            )
        lines.append("")

    # ── 논의 포인트 ──
    lines.append("---")
    lines.append("")
    lines.append("## 💡 회의 논의 포인트")
    lines.append("")
    if result.analyses:
        high_be = max(result.analyses, key=lambda a: a.breakeven_years)
        if high_be.breakeven_years > 15:
            lines.append(
                f"1. {high_be.region} 손익분기 {high_be.breakeven_years:.1f}년 — "
                f"장기 보유 전략 적합 여부 검토"
            )
    if result.mc_results:
        risky = max(result.mc_results, key=lambda m: m.prob_loss)
        if risky.prob_loss > 20:
            lines.append(
                f"2. {risky.region} 손실확률 {risky.prob_loss:.1f}% — "
                f"리스크 헤지 방안 논의 필요"
            )
    if result.analyses and len(result.analyses) >= 2:
        yields = sorted(result.analyses, key=lambda a: a.net_yield, reverse=True)
        spread = yields[0].net_yield - yields[-1].net_yield
        if spread > 1.0:
            lines.append(
                f"3. 권역 간 순수익률 격차 {spread:.2f}%p — "
                f"분산 투자 vs 집중 투자 전략 논의"
            )
    lines.append("")

    return "\n".join(lines)
