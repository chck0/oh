"""세금 시뮬레이터 — 취득세, 보유세(재산세+종합부동산세), 양도소득세.

한국 부동산 세제를 단순화하여 시나리오별 세후 수익률을 산출한다.
실제 세법은 매우 복잡하므로 참고용 추정치임을 명시한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaxParams:
    num_houses: int = 1
    holding_years: int = 5
    is_adjustment_area: bool = True
    long_term_deduction: bool = True


@dataclass
class AcquisitionTax:
    price: float
    rate_pct: float
    amount: float


@dataclass
class HoldingTax:
    yearly_property_tax: float
    yearly_comprehensive_tax: float
    total_annual: float
    total_over_period: float
    holding_years: int


@dataclass
class CapitalGainsTax:
    purchase_price: float
    sale_price: float
    gain: float
    deduction_pct: float
    taxable_gain: float
    tax_rate_pct: float
    tax_amount: float


@dataclass
class TaxSummary:
    region: str
    acquisition: AcquisitionTax
    holding: HoldingTax
    capital_gains: CapitalGainsTax
    total_tax: float
    effective_tax_rate_pct: float
    net_gain_after_tax: float


def _acquisition_tax_rate(price: float, num_houses: int) -> float:
    if num_houses >= 3:
        return 12.0
    if num_houses == 2:
        return 8.0
    if price > 90000:
        return 3.0
    if price > 60000:
        return 2.0
    return 1.1


def compute_acquisition_tax(price: float, num_houses: int = 1) -> AcquisitionTax:
    rate = _acquisition_tax_rate(price, num_houses)
    return AcquisitionTax(price=price, rate_pct=rate, amount=price * rate / 100)


def _property_tax(price: float) -> float:
    公시가율 = 0.7
    assessed = price * 公시가율
    if assessed <= 60000:
        return assessed * 0.001
    if assessed <= 150000:
        return 60 + (assessed - 60000) * 0.0015
    if assessed <= 300000:
        return 195 + (assessed - 150000) * 0.0025
    return 570 + (assessed - 300000) * 0.004


def _comprehensive_real_estate_tax(price: float, num_houses: int) -> float:
    公시가율 = 0.7
    assessed = price * 公시가율
    if num_houses <= 1:
        threshold = 110000
    else:
        threshold = 60000
    excess = assessed - threshold
    if excess <= 0:
        return 0.0
    if num_houses >= 3:
        rate = 0.012
    elif num_houses == 2:
        rate = 0.008
    else:
        rate = 0.005
    return excess * rate


def compute_holding_tax(
    price: float, num_houses: int = 1, holding_years: int = 5,
) -> HoldingTax:
    prop_tax = _property_tax(price)
    comp_tax = _comprehensive_real_estate_tax(price, num_houses)
    annual = prop_tax + comp_tax
    return HoldingTax(
        yearly_property_tax=round(prop_tax, 1),
        yearly_comprehensive_tax=round(comp_tax, 1),
        total_annual=round(annual, 1),
        total_over_period=round(annual * holding_years, 1),
        holding_years=holding_years,
    )


def _long_term_deduction_pct(holding_years: int, is_adjustment: bool) -> float:
    if is_adjustment:
        if holding_years >= 10:
            return 30.0
        if holding_years >= 5:
            return 20.0
        if holding_years >= 3:
            return 10.0
        return 0.0
    if holding_years >= 15:
        return 30.0
    if holding_years >= 10:
        return 20 + (holding_years - 10) * 2
    if holding_years >= 3:
        return 6 + (holding_years - 3) * 2
    return 0.0


def _capital_gains_rate(gain: float, num_houses: int, holding_years: int) -> float:
    if holding_years < 1:
        return 70.0
    if holding_years < 2:
        return 60.0
    if num_houses >= 3:
        return 68.0
    if num_houses == 2:
        return 58.0

    if gain <= 14000:
        return 6.0
    if gain <= 50000:
        return 15.0
    if gain <= 88000:
        return 24.0
    if gain <= 150000:
        return 35.0
    if gain <= 300000:
        return 38.0
    if gain <= 500000:
        return 40.0
    if gain <= 1000000:
        return 42.0
    return 45.0


def compute_capital_gains_tax(
    purchase_price: float,
    sale_price: float,
    *,
    num_houses: int = 1,
    holding_years: int = 5,
    is_adjustment_area: bool = True,
    long_term_deduction: bool = True,
) -> CapitalGainsTax:
    gain = sale_price - purchase_price
    if gain <= 0:
        return CapitalGainsTax(
            purchase_price=purchase_price, sale_price=sale_price,
            gain=gain, deduction_pct=0, taxable_gain=0,
            tax_rate_pct=0, tax_amount=0,
        )
    deduction = 0.0
    if long_term_deduction and num_houses <= 1:
        deduction = _long_term_deduction_pct(holding_years, is_adjustment_area)
    taxable = gain * (1 - deduction / 100)
    rate = _capital_gains_rate(taxable, num_houses, holding_years)
    tax = taxable * rate / 100
    return CapitalGainsTax(
        purchase_price=purchase_price, sale_price=sale_price,
        gain=round(gain, 1), deduction_pct=deduction,
        taxable_gain=round(taxable, 1),
        tax_rate_pct=rate, tax_amount=round(tax, 1),
    )


def compute_tax_summary(
    region: str,
    purchase_price: float,
    sale_price: float,
    params: TaxParams | None = None,
) -> TaxSummary:
    p = params or TaxParams()
    acq = compute_acquisition_tax(purchase_price, p.num_houses)
    hold = compute_holding_tax(purchase_price, p.num_houses, p.holding_years)
    cg = compute_capital_gains_tax(
        purchase_price, sale_price,
        num_houses=p.num_houses,
        holding_years=p.holding_years,
        is_adjustment_area=p.is_adjustment_area,
        long_term_deduction=p.long_term_deduction,
    )
    total = acq.amount + hold.total_over_period + cg.tax_amount
    gross_gain = sale_price - purchase_price
    net = gross_gain - total
    eff_rate = (total / gross_gain * 100) if gross_gain > 0 else 0
    return TaxSummary(
        region=region, acquisition=acq, holding=hold,
        capital_gains=cg, total_tax=round(total, 1),
        effective_tax_rate_pct=round(eff_rate, 1),
        net_gain_after_tax=round(net, 1),
    )


def compute_multi_tax_summary(
    analyses: list, params: TaxParams | None = None,
) -> list[TaxSummary]:
    results = []
    for a in analyses:
        appreciation = 1.02 ** (params.holding_years if params else 5)
        sale_price = a.avg_price * appreciation
        results.append(compute_tax_summary(
            a.region, a.avg_price, sale_price, params,
        ))
    return results


def format_tax_for_agents(summaries: list[TaxSummary]) -> str:
    if not summaries:
        return ""
    lines = ["═══ 세금 시뮬레이션 ═══\n"]
    for s in summaries:
        lines.append(f"■ {s.region}")
        lines.append(f"  취득세: {s.acquisition.amount:,.0f}만원 ({s.acquisition.rate_pct}%)")
        lines.append(f"  보유세(연): {s.holding.total_annual:,.0f}만원")
        lines.append(f"    재산세: {s.holding.yearly_property_tax:,.0f}만원")
        lines.append(f"    종합부동산세: {s.holding.yearly_comprehensive_tax:,.0f}만원")
        lines.append(f"  보유세({s.holding.holding_years}년): {s.holding.total_over_period:,.0f}만원")
        if s.capital_gains.gain > 0:
            lines.append(f"  양도차익: {s.capital_gains.gain:,.0f}만원")
            if s.capital_gains.deduction_pct > 0:
                lines.append(f"  장기보유공제: {s.capital_gains.deduction_pct}%")
            lines.append(f"  양도세: {s.capital_gains.tax_amount:,.0f}만원 ({s.capital_gains.tax_rate_pct}%)")
        lines.append(f"  ── 총 세금: {s.total_tax:,.0f}만원 (실효세율 {s.effective_tax_rate_pct}%)")
        lines.append(f"  ── 세후 순이익: {s.net_gain_after_tax:,.0f}만원")
        lines.append("")

    if len(summaries) > 1:
        lines.append("▸ 세후 수익 비교")
        best = max(summaries, key=lambda x: x.net_gain_after_tax)
        for s in summaries:
            marker = " ★" if s.region == best.region else ""
            lines.append(
                f"  {s.region}: 세후 {s.net_gain_after_tax:,.0f}만원 "
                f"(실효 {s.effective_tax_rate_pct}%){marker}"
            )
    return "\n".join(lines)
