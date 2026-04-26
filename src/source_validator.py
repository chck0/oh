"""Source citation validator: catch missing `[출처:]` on numeric claims.

Phase B.1 — MANIFESTO 가치 1 ("출처 있는 숫자만 말한다") 의 후처리 가드.
페르소나 프롬프트만으로는 LLM이 출처 표기를 깜빡할 수 있어 코드로 보강한다.

검출 단위 (재무 핵심만):  %, %p, 만원, 억원, 원, 배
통과 마커:                  [출처: ...], [추정 ...], [가정 ...], [프로필]
분리 단위:                  한국어 문장 (마침표·물음표·느낌표 후 공백/개행)

의도적으로 제외한 단위 — 주택/년/건/실 등은 사용자 프로필이나 일반 표현으로
자주 등장해 오탐을 유발하므로 1차 가드에서는 무시한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Numeric patterns that demand a source — financial claims only.
_NUMBER_RE = re.compile(
    r"\d+(?:[.,]\d+)*\s*(?:%p|%|만원|억원|원|배)"
)

# Markers that grant a citation for all numbers in the same sentence.
_SOURCE_MARKERS = ("[출처:", "[출처 :", "[추정", "[가정", "[프로필]")

# Sentence boundary: '.', '?', '!' followed by whitespace (including newlines).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class SourceWarning:
    rule: str
    message: str
    snippet: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}"


def split_sentences(text: str) -> list[str]:
    """Split a Korean response into sentences for per-sentence validation."""
    if not text:
        return []
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p for p in parts if p.strip()]


def find_numbers(text: str) -> list[str]:
    """Return raw matches of financial number patterns in a string."""
    return _NUMBER_RE.findall(text)


def has_source_marker(text: str) -> bool:
    """Whether a citation marker appears anywhere in the text."""
    return any(m in text for m in _SOURCE_MARKERS)


def validate_text(text: str) -> list[SourceWarning]:
    """Return warnings for sentences that contain a financial number but no
    source marker. A single marker covers every number in its sentence.
    """
    warnings: list[SourceWarning] = []
    for sentence in split_sentences(text):
        nums = find_numbers(sentence)
        if not nums:
            continue
        if has_source_marker(sentence):
            continue
        snippet = sentence.strip()
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        warnings.append(
            SourceWarning(
                rule="missing_source",
                message=f"수치 {nums!r}에 출처가 없습니다",
                snippet=snippet,
            )
        )
    return warnings
