"""PDF 리포트 생성 — 회의 결과를 전문적인 PDF 문서로 내보낸다.

fpdf2를 사용하며, 한글 출력을 위해 내장 latin-1 폰트 대신
유니코드 폰트가 없는 환경에서도 깨지지 않도록
한글을 영어 병기 방식으로 fallback 처리한다.
실제 배포 시 NanumGothic.ttf 등을 /assets 에 두면 한글 전체 렌더링 가능.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scorecard import Scorecard

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FONT_PATH = ASSETS_DIR / "NanumGothic.ttf"

VERDICT_EN = {
    "투자 추천": "INVEST",
    "조건부 추천": "CONDITIONAL",
    "대기": "WAIT",
    "패스": "PASS",
}

CATEGORY_EN = {
    "수익률": "Yield",
    "현금흐름": "Cashflow",
    "리스크": "Risk",
    "세금 효율": "Tax",
}


def _strip_md(text: str) -> str:
    """마크다운 기호를 제거하고 순수 텍스트를 반환한다."""
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^[\-\*]\s+", "  - ", text, flags=re.MULTILINE)
    return text


class _PDF(FPDF):
    def __init__(self, topic: str, started_at: datetime):
        super().__init__()
        self.topic = topic
        self.started_at = started_at
        self._has_unicode_font = False
        self._setup_font()

    def _setup_font(self) -> None:
        if FONT_PATH.exists():
            self.add_font("Nanum", "", str(FONT_PATH), uni=True)
            self.add_font("Nanum", "B", str(FONT_PATH), uni=True)
            self._has_unicode_font = True

    def _font(self, bold: bool = False, size: int = 11) -> None:
        if self._has_unicode_font:
            style = "B" if bold else ""
            self.set_font("Nanum", style, size)
        else:
            style = "B" if bold else ""
            self.set_font("Helvetica", style, size)

    def header(self) -> None:
        self._font(bold=True, size=9)
        self.set_text_color(100, 100, 100)
        header_text = "Real Estate Investment Advisory Report"
        self.cell(0, 8, header_text, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-15)
        self._font(size=8)
        self.set_text_color(130, 130, 130)
        date_str = self.started_at.strftime("%Y-%m-%d")
        self.cell(0, 10, f"Page {self.page_no()} | Generated {date_str}", align="C")
        self.set_text_color(0, 0, 0)


def _title_page(pdf: _PDF) -> None:
    pdf.add_page()
    pdf.ln(30)
    pdf.set_fill_color(21, 101, 192)
    pdf.rect(0, 60, 210, 60, "F")

    pdf.set_y(70)
    pdf.set_text_color(255, 255, 255)
    pdf._font(bold=True, size=20)
    topic_safe = pdf.topic if pdf._has_unicode_font else "Investment Advisory Report"
    pdf.multi_cell(0, 12, topic_safe, align="C")

    pdf.ln(6)
    pdf._font(size=12)
    date_str = pdf.started_at.strftime("%Y년 %m월 %d일") if pdf._has_unicode_font else pdf.started_at.strftime("%Y-%m-%d")
    pdf.cell(0, 10, date_str, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(130)
    pdf.set_text_color(80, 80, 80)
    pdf._font(size=10)
    members = "CFO  |  CSO  |  Investment Consultant  |  Clerk"
    pdf.cell(0, 8, members, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(200)
    pdf._font(size=9)
    pdf.set_text_color(150, 150, 150)
    disclaimer = "This report is for advisory purposes only. Investment decisions are the sole responsibility of the investor."
    pdf.multi_cell(0, 6, disclaimer, align="C")
    pdf.set_text_color(0, 0, 0)


def _scorecard_section(pdf: _PDF, cards: list[Scorecard]) -> None:
    if not cards:
        return
    pdf.add_page()
    pdf._font(bold=True, size=14)
    pdf.set_text_color(21, 101, 192)
    section_title = "투자 스코어카드" if pdf._has_unicode_font else "Investment Scorecard"
    pdf.cell(0, 10, section_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(21, 101, 192)
    pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    pdf.set_text_color(0, 0, 0)

    col_w = (190 - 50) / max(len(cards), 1)

    # Header row
    pdf._font(bold=True, size=10)
    pdf.set_fill_color(230, 240, 255)
    item_label = "항목" if pdf._has_unicode_font else "Category"
    pdf.cell(50, 8, item_label, border=1, fill=True)
    for card in cards:
        region_label = card.region if pdf._has_unicode_font else f"Region {cards.index(card)+1}"
        pdf.cell(col_w, 8, region_label, border=1, align="C", fill=True)
    pdf.ln()

    def _row(label_ko: str, label_en: str, values: list[str], bold: bool = False) -> None:
        pdf._font(bold=bold, size=9)
        label = label_ko if pdf._has_unicode_font else label_en
        pdf.cell(50, 7, label, border=1)
        for v in values:
            pdf.cell(col_w, 7, v, border=1, align="C")
        pdf.ln()

    total_scores = [f"{c.total_score}/{c.max_possible}pt" for c in cards]
    _row("종합 점수", "Total Score", total_scores, bold=True)

    verdicts = []
    for c in cards:
        v = (c.verdict if pdf._has_unicode_font else VERDICT_EN.get(c.verdict, c.verdict))
        verdicts.append(v)
    _row("판정", "Verdict", verdicts, bold=True)

    if cards[0].details:
        for i, detail in enumerate(cards[0].details):
            cat_ko = detail.category
            cat_en = CATEGORY_EN.get(cat_ko, cat_ko)
            scores = []
            for card in cards:
                d = card.details[i] if i < len(card.details) else None
                scores.append(f"{d.score:.0f}/{d.max_score:.0f}" if d else "N/A")
            _row(cat_ko, cat_en, scores)

    pdf.ln(4)
    # Ranking
    if len(cards) > 1:
        ranked = sorted(cards, key=lambda c: c.total_score, reverse=True)
        pdf._font(bold=True, size=10)
        rank_title = "종합 순위" if pdf._has_unicode_font else "Rankings"
        pdf.cell(0, 8, rank_title, new_x="LMARGIN", new_y="NEXT")
        pdf._font(size=9)
        for i, card in enumerate(ranked, 1):
            region = card.region if pdf._has_unicode_font else f"Region {i}"
            verdict = card.verdict if pdf._has_unicode_font else VERDICT_EN.get(card.verdict, card.verdict)
            pdf.cell(0, 6, f"  {i}. {region}  {card.total_score}pt  =>  {verdict}",
                     new_x="LMARGIN", new_y="NEXT")


def _highlights_section(pdf: _PDF, agent_highlights: list[dict]) -> None:
    """에이전트 핵심 발언 — role: agent 인 turns 중 앞 3개."""
    if not agent_highlights:
        return
    pdf.add_page()
    pdf._font(bold=True, size=14)
    pdf.set_text_color(21, 101, 192)
    section_title = "에이전트 핵심 발언" if pdf._has_unicode_font else "Agent Highlights"
    pdf.cell(0, 10, section_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(21, 101, 192)
    pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    pdf.set_text_color(0, 0, 0)

    for turn in agent_highlights[:6]:
        label = turn.get("label", turn.get("name", "Agent"))
        text = _strip_md(turn.get("text", turn.get("content", "")))
        if not text:
            continue

        pdf._font(bold=True, size=10)
        pdf.set_text_color(50, 50, 150)
        pdf.cell(0, 7, label, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf._font(size=9)
        snippet = text[:400] + ("..." if len(text) > 400 else "")
        if pdf._has_unicode_font:
            pdf.multi_cell(0, 6, snippet)
        else:
            safe = snippet.encode("ascii", errors="replace").decode("ascii")
            pdf.multi_cell(0, 6, safe)
        pdf.ln(3)


def _minutes_section(pdf: _PDF, minutes_text: str) -> None:
    if not minutes_text:
        return
    pdf.add_page()
    pdf._font(bold=True, size=14)
    pdf.set_text_color(21, 101, 192)
    section_title = "회의록 요약" if pdf._has_unicode_font else "Meeting Minutes"
    pdf.cell(0, 10, section_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(21, 101, 192)
    pdf.line(pdf.l_margin, pdf.get_y(), 210 - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    pdf.set_text_color(0, 0, 0)

    clean = _strip_md(minutes_text)
    lines = clean.splitlines()
    for line in lines[:80]:
        stripped = line.rstrip()
        if not stripped:
            pdf.ln(3)
            continue
        is_heading = line.startswith("  - ") or line.startswith("- ")
        pdf._font(bold=is_heading, size=9)
        if pdf._has_unicode_font:
            pdf.multi_cell(0, 6, stripped)
        else:
            safe = stripped.encode("ascii", errors="replace").decode("ascii")
            pdf.multi_cell(0, 6, safe)


def generate_pdf_report(
    topic: str,
    started_at: datetime,
    scorecards: list[Scorecard],
    minutes_text: str,
    agent_highlights: list[dict],
) -> bytes:
    """회의 결과 PDF를 생성하여 bytes로 반환한다."""
    pdf = _PDF(topic, started_at)
    pdf.set_auto_page_break(auto=True, margin=15)

    _title_page(pdf)
    _scorecard_section(pdf, scorecards)
    _highlights_section(pdf, agent_highlights)
    _minutes_section(pdf, minutes_text)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
