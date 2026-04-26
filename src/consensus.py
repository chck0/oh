"""합의/불일치 감지 — 에이전트 간 의견 수렴 시 자동 반론 주입.

세 C-suite가 모두 같은 방향으로 의견을 내면 확증 편향의 위험이 있으므로,
의장 개입 프롬프트를 생성하여 추가 토론을 유도한다.
"""
from __future__ import annotations

from enum import Enum

_POSITIVE = {"추천", "긍정", "유리", "매력", "좋은", "적합", "가능", "투자할", "괜찮"}
_NEGATIVE = {"위험", "리스크", "불리", "주의", "보류", "부정", "마이너스", "부적합",
             "안 맞", "불안", "하락", "급등", "과열", "손실"}


class Sentiment(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"


def detect_sentiment(text: str) -> Sentiment:
    pos = sum(1 for kw in _POSITIVE if kw in text)
    neg = sum(1 for kw in _NEGATIVE if kw in text)
    if pos > neg and pos >= 2:
        return Sentiment.POSITIVE
    if neg > pos and neg >= 2:
        return Sentiment.NEGATIVE
    return Sentiment.MIXED


def detect_consensus(turns: list[dict]) -> tuple[bool, str]:
    sentiments = [detect_sentiment(t["text"]) for t in turns if t.get("role") == "agent"]
    if not sentiments:
        return False, "empty"
    if all(s == Sentiment.POSITIVE for s in sentiments):
        return True, "all_positive"
    if all(s == Sentiment.NEGATIVE for s in sentiments):
        return True, "all_negative"
    return False, "mixed"


def build_challenge_prompt(consensus_type: str) -> str:
    if consensus_type == "all_positive":
        return (
            "[의장 개입] 세 분 모두 긍정적인 평가입니다. 확증 편향의 위험이 있습니다. "
            "이 투자의 가장 큰 약점이나 실패 시나리오를 한 가지씩 지적해 주세요."
        )
    if consensus_type == "all_negative":
        return (
            "[의장 개입] 세 분 모두 부정적인 평가입니다. "
            "혹시 놓치고 있는 기회가 있지는 않은지, 긍정적 측면을 한 가지씩 짚어주세요."
        )
    return ""
