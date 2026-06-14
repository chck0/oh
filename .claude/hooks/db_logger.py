#!/usr/bin/env python3
"""
PostToolUse 훅 — Claude 가 'DB 를 바꾸는' 도구를 실행할 때마다 즉시 그 명령/SQL 을
docs/worklog/.raw/<이름>-db.md 에 기록한다.

왜:
    사용자가 따로 DB 편집기를 안 쓰고 Claude 를 통해 작업하면, DB 수정은 전부
    Claude 의 도구 호출(Bash/PowerShell 의 sqlite 명령, .sql/.py 마이그레이션 실행,
    .sql 파일 편집)로 일어난다. 그 순간을 잡아 SQL/명령 텍스트를 남긴다.
    git 은 data/*.db(바이너리)를 추적하지 않으므로, 이 로그가 'DB 에 무슨 일이
    있었는지'의 유일한 자동 기록이 된다.

특징:
    - LLM 없음 → 토큰 0, 빠름. 무슨 일이 있어도 사용자를 막지 않는다(항상 exit 0).
    - DB 를 '변경'하는 작업만 골라 잡는다. 단순 조회(SELECT)나 무관한 도구는 무시.
    - settings.json 의 matcher 로 Bash/PowerShell/Edit/Write 에서만 호출되게 해
      불필요한 발동을 줄인다.

입력: stdin 으로 PostToolUse 훅 JSON (tool_name, tool_input, cwd, session_id 등)
"""
import sys
import os
import re
import json
from datetime import datetime

# DB 를 '변경'하는 신호 (대소문자 무시). SELECT 는 일부러 제외.
_MUTATION = re.compile(
    r"\b(ALTER\s+TABLE|CREATE\s+TABLE|DROP\s+TABLE|INSERT\s+INTO|UPDATE\s+\w+\s+SET"
    r"|DELETE\s+FROM|CREATE\s+INDEX|DROP\s+INDEX|TRUNCATE|REPLACE\s+INTO"
    r"|ADD\s+COLUMN|RENAME\s+TO|VACUUM)\b",
    re.IGNORECASE,
)
# DB 를 만지는 도구/스크립트 신호
_DB_TOOL = re.compile(
    r"(sqlite3|\.db\b|psql\b|\.sql\b|migrat)",
    re.IGNORECASE,
)


def _read_event() -> dict:
    try:
        data = sys.stdin.buffer.read()
        text = data.decode("utf-8-sig", errors="replace").strip()
        return json.loads(text or "{}")
    except Exception:
        return {}


def _author(root: str) -> str:
    f = os.path.join(root, "docs", "worklog", ".author")
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:
            name = fh.read().strip()
            if name:
                return name
    except Exception:
        pass
    return "unknown"


def _safe_name(name: str) -> str:
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip() or "unknown"


def _oneline(text: str, limit: int = 1000) -> str:
    s = " ".join(text.split())
    return s[:limit] + "…" if len(s) > limit else s


def _detect(tool_name: str, tool_input: dict) -> str | None:
    """DB 변경이면 기록할 한 줄을 돌려주고, 아니면 None."""
    if tool_name in ("Bash", "PowerShell"):
        cmd = str(tool_input.get("command", ""))
        if _MUTATION.search(cmd) or (_DB_TOOL.search(cmd) and _MUTATION.search(cmd)):
            return f"[{tool_name}] {_oneline(cmd)}"
        # sqlite3/.sql 을 mutation 없이 실행하는 경우(스크립트 파일 실행 등)도 포착
        if _DB_TOOL.search(cmd) and (".sql" in cmd.lower() or "migrat" in cmd.lower()):
            return f"[{tool_name}] {_oneline(cmd)}"
        return None
    if tool_name in ("Edit", "Write"):
        path = str(tool_input.get("file_path", ""))
        if path.lower().endswith(".sql"):
            verb = "작성" if tool_name == "Write" else "수정"
            return f"[{tool_name}] SQL 파일 {verb}: {path}"
        return None
    return None


def main() -> None:
    event = _read_event()
    root = event.get("cwd") or os.getcwd()
    tool_name = event.get("tool_name") or ""
    tool_input = event.get("tool_input") or {}
    session_id = (event.get("session_id") or event.get("sessionId") or "session")[:8]

    if not isinstance(tool_input, dict):
        return

    entry = _detect(tool_name, tool_input)
    if not entry:
        return  # DB 변경 아님 → 조용히 종료

    raw_dir = os.path.join(root, "docs", "worklog", ".raw")
    try:
        os.makedirs(raw_dir, exist_ok=True)
    except Exception:
        return

    author = _safe_name(_author(root))
    db_file = os.path.join(raw_dir, f"{author}-db.md")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        new = not os.path.exists(db_file)
        with open(db_file, "a", encoding="utf-8") as fh:
            if new:
                fh.write("# DB 변경 로그 (자동 기록 · 로컬 전용)\n")
                fh.write("\n> Claude 가 실행한 DB 변경 명령/SQL 을 그때그때 적립합니다.\n")
                fh.write("> '올려줘' 시 worklog 의 'DB 변경' 항목으로 정리됩니다.\n")
            fh.write(f"\n- {now} (s:{session_id}) {entry}")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
