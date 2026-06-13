#!/usr/bin/env python3
"""
PreCompact 훅 — 컨텍스트 '압축' 직전에 호출되어, 그동안의 작업 흔적을
docs/worklog/.raw/<이름>.md 에 값싸게(=LLM 없이) 적립한다.

왜 필요한가:
    긴 세션에서 컨텍스트가 압축되면 앞부분("이거 했다가 되돌렸다" 같은) 기억이
    Claude의 활성 컨텍스트에서 사라진다. 압축 '직전'에 유저 요청 흐름과 바뀐 파일을
    텍스트로 남겨두면, 나중에 커밋 시점에 Claude가 이 raw 기록을 읽어 깔끔한
    worklog 로 정리할 수 있다.

특징:
    - LLM/네트워크 호출 없음 → 토큰 0, 거의 안 깨짐, 빠름
    - 무슨 일이 있어도 사용자를 막지 않는다 (항상 exit 0)
    - 세션별 커서를 둬서 같은 내용을 중복 적립하지 않는다

입력: stdin 으로 훅 JSON (transcript_path, session_id, cwd 등)
"""
import sys
import os
import json
import subprocess
from datetime import datetime


def _read_event() -> dict:
    try:
        # stdin 을 '바이너리'로 읽고 utf-8-sig 로 디코딩한다.
        # - Windows 콘솔 코드페이지(cp949 등)에 영향받지 않게 함
        # - utf-8-sig 는 앞에 BOM 이 있으면 자동으로 벗겨준다
        data = sys.stdin.buffer.read()
        text = data.decode("utf-8-sig", errors="replace").strip()
        return json.loads(text or "{}")
    except Exception:
        return {}


def _project_root(event: dict) -> str:
    # 훅은 보통 프로젝트 루트에서 실행되지만, stdin 의 cwd 를 우선 신뢰
    return event.get("cwd") or os.getcwd()


def _author(root: str) -> str:
    """docs/worklog/.author 우선 → git user.name → 'unknown'"""
    f = os.path.join(root, "docs", "worklog", ".author")
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:  # BOM 있으면 벗김
            name = fh.read().strip()
            if name:
                return name
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["git", "config", "user.name"],
            cwd=root, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return "unknown"


def _safe_name(name: str) -> str:
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip() or "unknown"


def _oneline(text: str, limit: int) -> str:
    s = " ".join(text.split())
    return s[:limit] + "…" if len(s) > limit else s


def _extract_dialogue(transcript_path: str, start_line: int) -> tuple[list[tuple], int]:
    """start_line 이후 줄에서 (역할, 텍스트) 흐름을 시간 순서대로 뽑는다.

    - 'user'    : 사용자가 실제 타이핑한 요청 (시스템/툴 노이즈 제외)
    - 'claude'  : Claude 가 대화창에 쓴 설명(=무엇을 어떻게 왜 했는지). 툴 호출은 제외하고
                  순수 text 블록만. 이게 '판단/방향/수정 내용'을 담는다.
    """
    items: list[tuple] = []
    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except Exception:
        return items, start_line
    total = len(lines)
    for line in lines[start_line:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        typ = obj.get("type")
        msg = obj.get("message", {}) or {}
        role = msg.get("role")
        content = msg.get("content")

        # 순수 text 추출 (str 그대로 / list 면 text 블록만)
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        else:
            text = ""
        if not text:
            continue

        if typ == "user" and role == "user":
            low = text[:60]
            if (
                text.startswith("<")
                or text.startswith("Caveat:")
                or text.startswith("[Request interrupted")
                or "system-reminder" in low
                or "command-name" in low
                or "local-command" in low
            ):
                continue
            items.append(("user", _oneline(text, 200)))
        elif typ == "assistant" and role == "assistant":
            items.append(("claude", _oneline(text, 320)))
    return items, total


def _changed_files(root: str) -> str:
    try:
        out = subprocess.run(
            ["git", "status", "--short"],
            cwd=root, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return out
    except Exception:
        return ""


def main() -> None:
    event = _read_event()
    root = _project_root(event)
    transcript = event.get("transcript_path") or ""
    session_id = (event.get("session_id") or event.get("sessionId") or "session")[:8]

    if not transcript or not os.path.exists(transcript):
        return

    raw_dir = os.path.join(root, "docs", "worklog", ".raw")
    os.makedirs(raw_dir, exist_ok=True)

    cursor_file = os.path.join(raw_dir, f".cursor-{session_id}")
    try:
        with open(cursor_file, "r", encoding="utf-8") as fh:
            start_line = int(fh.read().strip() or "0")
    except Exception:
        start_line = 0

    items, total = _extract_dialogue(transcript, start_line)
    if not items:
        # 적립할 새 내용이 없으면 커서만 갱신하고 종료
        try:
            with open(cursor_file, "w", encoding="utf-8") as fh:
                fh.write(str(total))
        except Exception:
            pass
        return

    author = _safe_name(_author(root))
    changed = _changed_files(root)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    block = [f"\n### ⏱ 압축 백업 — {now} (session {session_id})\n"]
    block.append("**작업 흐름 (🧑 요청 ↔ 🤖 Claude가 한 일):**")
    for role, text in items:
        icon = "🧑" if role == "user" else "🤖"
        block.append(f"- {icon} {text}")
    if changed:
        block.append("\n**현재 변경된 파일:**")
        block.append("```")
        block.append(changed)
        block.append("```")
    block.append("\n---")

    raw_file = os.path.join(raw_dir, f"{author}.md")
    try:
        with open(raw_file, "a", encoding="utf-8") as fh:
            fh.write("\n".join(block) + "\n")
        with open(cursor_file, "w", encoding="utf-8") as fh:
            fh.write(str(total))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 절대 사용자를 막지 않는다
    sys.exit(0)
