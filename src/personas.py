"""Load persona markdown files and build system prompts for each agent.

페르소나 명세서는 /agents/*.md에 있어서, 프롬프트 튜닝이
코드 변경이 아닌 파일 편집으로 가능하다.
(Premortem 시나리오 3 "영역 침범" 대응)
"""
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"

AGENT_CONFIG = {
    "practitioner": {
        "name": "CFO",
        "label": "재무총괄",
        "file": "practitioner.md",
        "emoji": "📊",
    },
    "redteam": {
        "name": "CSO",
        "label": "전략총괄",
        "file": "redteam.md",
        "emoji": "🔴",
    },
    "mentor": {
        "name": "투자컨설턴트",
        "label": "투자자문",
        "file": "mentor.md",
        "emoji": "🧭",
    },
    "clerk": {
        "name": "비서실장",
        "label": "서기",
        "file": "clerk.md",
        "emoji": "📝",
    },
}


DIVERSITY_ANGLES: dict[str, list[str]] = {
    "practitioner": ["수익률", "대출", "세금", "현금흐름", "감가상각", "비교"],
    "redteam": ["타이밍", "입지", "경쟁", "정책", "시나리오", "하방", "전제", "대안"],
    "mentor": ["적합성", "대안", "포트폴리오", "리스크프로파일", "유형", "출구", "생애주기", "기회비용"],
}


def build_diversity_reminder(agent_key: str, used_angles: list[str]) -> str:
    all_angles = DIVERSITY_ANGLES.get(agent_key, [])
    if not all_angles:
        return ""
    unused = [a for a in all_angles if a not in used_angles]
    if not unused:
        return ""
    return (
        f"[다양성 리마인더] 아직 사용하지 않은 관점: {', '.join(unused[:3])}. "
        "이번 턴에는 이 중 하나를 시도해보세요."
    )


def detect_used_angles(agent_key: str, text: str) -> list[str]:
    all_angles = DIVERSITY_ANGLES.get(agent_key, [])
    return [a for a in all_angles if a in text]


def load_persona_spec(agent_key: str) -> str:
    """Read the raw markdown persona specification."""
    cfg = AGENT_CONFIG[agent_key]
    return (AGENTS_DIR / cfg["file"]).read_text(encoding="utf-8")


def build_system_prompt(agent_key: str) -> str:
    """Wrap the persona spec into a system prompt for the LLM."""
    spec = load_persona_spec(agent_key)
    return f"""당신은 "Data 기반 Multi-Agent 부동산 투자 자문 시스템"의 C-suite 회의 참석자입니다.
아래 페르소나 명세서를 **엄격히** 따라 응답하세요.

규칙:
- 반드시 한국어로 응답
- 페르소나 명세서의 Must-Do / Must-Not 규칙을 모두 준수
- **최대 3~4문장** (비서실장의 회의록은 예외 — 템플릿을 따를 것)
- 페르소나 명세서의 "다양성 원칙" 표에 있는 각도를 **매 턴마다 번갈아 사용**
  (같은 각도의 반복은 단조로움 = 실패)
- **자기 영역만 발언** — 영역 경계를 넘으면 실패
  · CFO: 수익률/세금/대출/현금흐름만
  · CSO: 타이밍/입지/리스크/경쟁만
  · 투자컨설턴트: 투자 적합성/포트폴리오/대안 비교/리스크 프로파일만
- CFO는 모든 수치에 [출처: ___]를 명시할 것
- 캐릭터를 절대 깨지 마세요 (시스템·메타정보 언급 금지)
- 다른 참석자의 발언이 먼저 나왔다면 참고하되, 동일 내용을 반복하지 마세요

=== 페르소나 명세서 ===
{spec}
=== 명세서 끝 ===

이제 회의에서 당신이 발언할 차례입니다. 페르소나에 충실히 응답하세요.
"""
