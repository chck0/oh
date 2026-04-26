"""Meeting archive: Obsidian-compatible frontmatter, past-meeting loading,
and session checkpointing.

Stage 2 핵심 모듈 — WhyTree 줄기 3 ("결정하고 나면 흐지부지된다") 대응.
- 회의록에 YAML frontmatter 추가 → 옵시디언 Vault 에 그대로 드롭 가능
- 새 회의 시작 시 관련 과거 회의록 자동 로드 → RAG 라이트 버전
- 세션 체크포인트(JSON) → 중단된 회의 재개 가능
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MEETINGS_DIR = REPO_ROOT / "meetings"
SESSIONS_DIR = MEETINGS_DIR / ".sessions"


# ----------------------------------------------------------------------
# Obsidian frontmatter
# ----------------------------------------------------------------------


def build_frontmatter(
    *,
    topic: str,
    started_at: datetime,
    tags: list[str] | None = None,
    participants: list[str] | None = None,
) -> str:
    """Build Obsidian-compatible YAML frontmatter block (including the
    delimiters)."""
    tags = tags or ["meeting", "talkfile"]
    participants = participants or ["대표님", "CFO", "CSO", "투자컨설턴트", "기록"]
    tag_yaml = ", ".join(f'"{_escape(t)}"' for t in tags)
    part_yaml = ", ".join(f'"{_escape(p)}"' for p in participants)
    return (
        "---\n"
        f'date: "{started_at.strftime("%Y-%m-%d")}"\n'
        f'time: "{started_at.strftime("%H:%M")}"\n'
        f'topic: "{_escape(topic)}"\n'
        f"participants: [{part_yaml}]\n"
        f"tags: [{tag_yaml}]\n"
        "---\n"
    )


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Minimal YAML-like parser for our fixed frontmatter schema.
    Returns (metadata_dict, body_without_frontmatter)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    header, body = m.group(1), m.group(2)
    data: dict[str, Any] = {}
    for line in header.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        val = raw.strip()
        # List: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            parts = [
                p.strip().strip('"').strip("'")
                for p in inner.split(",")
                if p.strip()
            ]
            data[key] = parts
            continue
        # Quoted string
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        data[key] = val
    return data, body


def _escape(s: str) -> str:
    return s.replace('"', '\\"')


# ----------------------------------------------------------------------
# Meeting listing
# ----------------------------------------------------------------------


@dataclass
class MeetingRecord:
    path: Path
    topic: str
    date: str
    time: str
    tags: list[str]
    summary: str  # first ~300 chars of body

    @property
    def datetime_sort_key(self) -> str:
        return f"{self.date}T{self.time}"


def list_meetings(include_mock: bool = False) -> list[MeetingRecord]:
    """List all meeting records in reverse chronological order."""
    if not MEETINGS_DIR.exists():
        return []
    records: list[MeetingRecord] = []
    for path in sorted(MEETINGS_DIR.glob("*.md")):
        if not include_mock and "MOCK" in path.name:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = parse_frontmatter(content)
        topic = meta.get("topic") or path.stem
        date = meta.get("date") or _guess_date_from_name(path.stem)
        time = meta.get("time") or ""
        raw_tags = meta.get("tags", [])
        tags = raw_tags if isinstance(raw_tags, list) else []
        summary = ""
        if body:
            # Pick the first non-header paragraph
            for chunk in body.strip().split("\n\n"):
                chunk = chunk.strip()
                if chunk and not chunk.startswith("#"):
                    summary = chunk[:300]
                    break
        records.append(
            MeetingRecord(
                path=path,
                topic=topic,
                date=date,
                time=time,
                tags=tags,
                summary=summary,
            )
        )
    records.sort(key=lambda r: r.datetime_sort_key, reverse=True)
    return records


def _guess_date_from_name(stem: str) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", stem)
    return m.group(1) if m else ""


# ----------------------------------------------------------------------
# Past-context retrieval (Stage 2 = keyword; Stage 6 will upgrade to RAG)
# ----------------------------------------------------------------------


def find_relevant_meetings(
    topic: str,
    limit: int = 3,
    keyword_fallback: bool = True,
) -> list[MeetingRecord]:
    """Return up to `limit` meetings most relevant to `topic`.

    Stage 2 strategy (no embeddings yet):
    1. Keyword overlap against topic + summary tokens
    2. Fallback: most recent `limit` meetings if nothing matches
    """
    all_meetings = list_meetings()
    if not all_meetings:
        return []

    topic_tokens = set(_tokenize(topic))
    scored: list[tuple[int, MeetingRecord]] = []
    for m in all_meetings:
        meeting_tokens = set(_tokenize(m.topic)) | set(_tokenize(m.summary))
        overlap = len(topic_tokens & meeting_tokens)
        if overlap > 0:
            scored.append((overlap, m))

    if scored:
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:limit]]

    if keyword_fallback:
        return all_meetings[:limit]
    return []


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: keep ASCII alnum and Hangul runs, drop short tokens."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+|[가-힣]+", text)
    return [t for t in tokens if len(t) >= 2]


def build_context_block(meetings: list[MeetingRecord]) -> str:
    """Build a text block of past meetings for injection into the agent
    conversation as a 'user' message."""
    if not meetings:
        return ""
    lines = ["=== 📚 참고: 과거 회의 맥락 ==="]
    for m in meetings:
        header = f"• {m.date} {m.time} — {m.topic}".rstrip()
        lines.append("")
        lines.append(header)
        if m.summary:
            lines.append(m.summary)
    lines.append("")
    lines.append("=== 과거 회의 맥락 끝 ===")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Session checkpointing
# ----------------------------------------------------------------------


def save_session(session_id: str, data: dict[str, Any]) -> Path:
    """Persist the transcript/state to JSON so a crashed meeting can resume."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_session(session_id: str) -> dict[str, Any] | None:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_sessions() -> list[str]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted([p.stem for p in SESSIONS_DIR.glob("*.json")])


def delete_session(session_id: str) -> bool:
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
