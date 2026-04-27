"""지역 비교 — 두 지역의 스코어카드를 나란히 비교하는 유틸리티."""
from __future__ import annotations

from scorecard import Scorecard


def format_comparison_table_md(cards: list[Scorecard]) -> str:
    """두 지역 스코어카드를 Markdown 테이블로 나란히 반환한다."""
    if len(cards) < 2:
        return ""
    header = "| 항목 | " + " | ".join(c.region for c in cards) + " |"
    sep = "| :--- |" + " :---: |" * len(cards)
    rows = [header, sep]

    rows.append(
        "| **종합 점수** | "
        + " | ".join(f"**{c.total_score}점**" for c in cards)
        + " |"
    )
    rows.append(
        "| **판정** | "
        + " | ".join(f"**{c.verdict}**" for c in cards)
        + " |"
    )

    for i, detail in enumerate(cards[0].details):
        cat = detail.category
        scores = []
        for card in cards:
            d = card.details[i] if i < len(card.details) else None
            scores.append(f"{d.score:.0f}/{d.max_score:.0f}점" if d else "N/A")
        rows.append(f"| {cat} | " + " | ".join(scores) + " |")

    rows.append(
        "| **강점** | "
        + " | ".join("; ".join(c.key_strengths) or "—" for c in cards)
        + " |"
    )
    rows.append(
        "| **리스크** | "
        + " | ".join("; ".join(c.key_risks) or "—" for c in cards)
        + " |"
    )

    # 승자 판정
    best = max(cards, key=lambda c: c.total_score)
    rows.append("")
    rows.append(
        f"> **종합 우위**: {best.region} "
        f"({best.total_score}점 / {best.verdict})"
    )
    return "\n".join(rows)


def build_comparison_first_message(regions: list[str]) -> str:
    """비교 회의 시작 시 에이전트에게 전달할 첫 번째 질문."""
    region_str = " vs ".join(regions)
    return (
        f"{region_str} — 두 지역을 정량·정성 모두 비교하여 "
        "어디에 투자하는 게 더 유리한지 각자의 관점에서 분석해 주세요."
    )
