"""User investment profile: persist client context across meetings.

Phase A.1 — eliminates re-entering risk profile, budget, holding plans every
meeting. The 투자컨설턴트 agent uses this profile to make truly client-specific
recommendations (MANIFESTO 핵심 가치 2 — "각자의 자리에서 발언").

Storage: profiles/{name}.json — git-ignored except `example.json`.
JSON (not YAML) for consistency with archive.py and zero new dependencies.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO_ROOT / "profiles"
DEFAULT_NAME = "default"

RISK_PROFILES: dict[str, str] = {
    "conservative": "보수적",
    "moderate": "중립적",
    "aggressive": "공격적",
}

INVESTMENT_GOALS: dict[str, str] = {
    "rental": "월세 수익형",
    "capital_gain": "시세차익형",
    "mixed": "혼합형 (월세 + 시세차익)",
}

LIFE_STAGES: dict[str, str] = {
    "accumulation": "자산 형성기",
    "expansion": "자산 확장기",
    "preservation": "자산 보존기",
}


@dataclass
class Profile:
    """Investment profile of the client (대표님)."""

    nickname: str = "대표님"
    risk_profile: str = "moderate"          # conservative / moderate / aggressive
    investment_goal: str = "rental"         # rental / capital_gain / mixed
    budget_manwon: int = 0                  # 가용 예산 (만원). 0 = 미입력
    property_count: int = 1                 # 보유 주택 수 (0=무주택, 1=1주택, ...)
    holding_years: int = 5                  # 투자 시계 (년)
    life_stage: str = "expansion"           # accumulation / expansion / preservation
    notes: str = ""                         # 자유 메모

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        # Keep only known fields so future schema additions don't break old files
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    @property
    def risk_label(self) -> str:
        return RISK_PROFILES.get(self.risk_profile, self.risk_profile)

    @property
    def goal_label(self) -> str:
        return INVESTMENT_GOALS.get(self.investment_goal, self.investment_goal)

    @property
    def life_stage_label(self) -> str:
        return LIFE_STAGES.get(self.life_stage, self.life_stage)


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------


def save_profile(
    profile: Profile,
    name: str = DEFAULT_NAME,
    *,
    profiles_dir: Path | None = None,
) -> Path:
    """Persist a profile to JSON."""
    base = profiles_dir or PROFILES_DIR
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{name}.json"
    path.write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_profile(
    name: str = DEFAULT_NAME,
    *,
    profiles_dir: Path | None = None,
) -> Profile | None:
    """Load a profile by name. Returns None if missing."""
    base = profiles_dir or PROFILES_DIR
    path = base / f"{name}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Profile.from_dict(data)


def list_profiles(*, profiles_dir: Path | None = None) -> list[str]:
    """List available profile names (without .json suffix), sorted."""
    base = profiles_dir or PROFILES_DIR
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.json"))


def delete_profile(
    name: str,
    *,
    profiles_dir: Path | None = None,
) -> bool:
    base = profiles_dir or PROFILES_DIR
    path = base / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# ----------------------------------------------------------------------
# Agent context formatting
# ----------------------------------------------------------------------


def _format_budget(manwon: int) -> str:
    if manwon <= 0:
        return "미입력"
    if manwon >= 10000:
        eok = manwon // 10000
        rest = manwon % 10000
        if rest == 0:
            return f"{eok}억원"
        return f"{eok}억 {rest:,}만원"
    return f"{manwon:,}만원"


def _format_property_count(n: int) -> str:
    if n <= 0:
        return "무주택"
    if n >= 3:
        return f"{n}주택 (다주택자)"
    return f"{n}주택"


def format_for_agents(profile: Profile | None) -> str:
    """Build a transcript block to inject as a 'user' message at meeting start.

    Mirrors the style of `real_estate.format_for_agents` and
    `archive.build_context_block` so the agents see a familiar shape.
    """
    if profile is None:
        return ""
    lines = [
        "=== 👤 사용자(대표님) 투자 프로필 ===",
        f"- 별칭: {profile.nickname}",
        f"- 리스크 프로파일: {profile.risk_label}",
        f"- 투자 목적: {profile.goal_label}",
        f"- 가용 예산: {_format_budget(profile.budget_manwon)}",
        f"- 보유 주택 수: {_format_property_count(profile.property_count)}",
        f"- 투자 시계: {profile.holding_years}년 보유 계획",
        f"- 생애주기: {profile.life_stage_label}",
    ]
    if profile.notes.strip():
        lines.append(f"- 메모: {profile.notes.strip()}")
    lines.append("")
    lines.append(
        "투자컨설턴트는 이 프로필에 기반해 적합성을 자문하세요. "
        "CFO·CSO도 참고하되 자기 영역을 벗어나지 마세요."
    )
    lines.append("=== 프로필 끝 ===")
    return "\n".join(lines)
