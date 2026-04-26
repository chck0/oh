"""Tests for personas module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from personas import AGENT_CONFIG, load_persona_spec, build_system_prompt


class TestAgentConfig:
    def test_has_all_agents(self):
        for key in ["practitioner", "redteam", "mentor", "clerk"]:
            assert key in AGENT_CONFIG

    def test_agent_has_required_fields(self):
        for key, cfg in AGENT_CONFIG.items():
            assert "name" in cfg, f"{key} missing name"
            assert "label" in cfg, f"{key} missing label"
            assert "emoji" in cfg, f"{key} missing emoji"
            assert "file" in cfg, f"{key} missing file"

    def test_names_korean(self):
        names = {cfg["name"] for cfg in AGENT_CONFIG.values()}
        assert "CFO" in names
        assert "CSO" in names
        assert "투자컨설턴트" in names
        assert "비서실장" in names


class TestLoadPersonaSpec:
    def test_loads_practitioner(self):
        spec = load_persona_spec("practitioner")
        assert len(spec) > 100

    def test_loads_all_agents(self):
        for key in AGENT_CONFIG:
            spec = load_persona_spec(key)
            assert isinstance(spec, str)
            assert len(spec) > 50


class TestBuildSystemPrompt:
    def test_contains_persona_spec(self):
        prompt = build_system_prompt("practitioner")
        assert "페르소나 명세서" in prompt

    def test_contains_boundary_rules(self):
        prompt = build_system_prompt("practitioner")
        assert "영역 경계" in prompt or "자기 영역만" in prompt

    def test_contains_korean_instruction(self):
        prompt = build_system_prompt("redteam")
        assert "한국어" in prompt


class TestAgentBoundaryRules:
    """PREMORTEM 시나리오 3 대응 — 각 에이전트의 영역 경계가 프롬프트에 명시되어 있는지 검증."""

    def test_cfo_boundary_in_system_prompt(self):
        prompt = build_system_prompt("practitioner")
        assert "수익률" in prompt and "세금" in prompt
        assert "자기 영역만" in prompt or "영역 경계" in prompt

    def test_cso_boundary_in_system_prompt(self):
        prompt = build_system_prompt("redteam")
        assert "타이밍" in prompt or "리스크" in prompt
        assert "자기 영역만" in prompt or "영역 경계" in prompt

    def test_consultant_boundary_in_system_prompt(self):
        prompt = build_system_prompt("mentor")
        assert "적합성" in prompt or "포트폴리오" in prompt
        assert "자기 영역만" in prompt or "영역 경계" in prompt

    def test_cfo_spec_forbids_strategy(self):
        spec = load_persona_spec("practitioner")
        assert "CSO" in spec or "전략" in spec
        assert "투자컨설턴트" in spec or "적합성" in spec

    def test_cso_spec_forbids_tax_calculation(self):
        spec = load_persona_spec("redteam")
        assert "세금" in spec or "재무" in spec or "CFO" in spec

    def test_consultant_spec_forbids_detailed_numbers(self):
        spec = load_persona_spec("mentor")
        assert "수치 계산" in spec or "CFO" in spec

    def test_cfo_must_cite_sources(self):
        spec = load_persona_spec("practitioner")
        assert "출처" in spec
        assert "[출처:" in spec or "[출처: ___]" in spec

    def test_cso_must_raise_risk(self):
        spec = load_persona_spec("redteam")
        assert "리스크" in spec
        assert "반론" in spec or "반드시" in spec


class TestHallucinationGuards:
    """PREMORTEM 시나리오 2 대응 — 데이터 없을 때 안전한 응답을 하는지 검증."""

    def test_cfo_spec_has_no_data_fallback(self):
        spec = load_persona_spec("practitioner")
        assert "데이터" in spec and ("확인" in spec or "부족" in spec)

    def test_cfo_prompt_forbids_guessing(self):
        prompt = build_system_prompt("practitioner")
        assert "느낌" in prompt or "아마" in prompt or "출처" in prompt

    def test_empty_summaries_return_empty_text(self):
        from real_estate import format_for_agents
        assert format_for_agents([]) == ""

    def test_empty_analyses_return_empty_text(self):
        from yield_analyzer import format_analysis_for_agents
        assert format_analysis_for_agents([]) == ""

    def test_empty_tax_returns_empty_text(self):
        from tax import format_tax_for_agents
        assert format_tax_for_agents([]) == ""

    def test_empty_scorecard_returns_empty_text(self):
        from scorecard import format_scorecard_for_agents
        assert format_scorecard_for_agents([]) == ""

    def test_empty_portfolio_returns_empty_text(self):
        from portfolio import format_portfolio_for_agents
        assert format_portfolio_for_agents([]) == ""

    def test_empty_cashflow_returns_empty_text(self):
        from cashflow import format_cashflow_for_agents
        assert format_cashflow_for_agents([]) == ""

    def test_empty_montecarlo_returns_empty_text(self):
        from monte_carlo import format_monte_carlo_for_agents
        assert format_monte_carlo_for_agents([]) == ""

    def test_unknown_region_gets_sample_data(self):
        from real_estate import get_region_data
        result = get_region_data("알수없는구")
        assert result.is_sample is True


class TestProfileGuidance:
    """Phase A.4 — 페르소나 명세서가 사용자 프로필 블록을 활용하도록 가이드되는지 검증."""

    def test_mentor_spec_mentions_profile(self):
        spec = load_persona_spec("mentor")
        assert "프로필" in spec, "mentor.md에 '프로필' 가이드 섹션 누락"

    def test_mentor_spec_maps_all_risk_profile_levels(self):
        spec = load_persona_spec("mentor")
        for level in ["보수적", "중립적", "공격적"]:
            assert level in spec, f"mentor.md에 '{level}' 프로파일 톤 매핑 누락"

    def test_mentor_spec_maps_investment_goal_types(self):
        spec = load_persona_spec("mentor")
        assert "월세" in spec
        assert "시세차익" in spec or "시세 차익" in spec

    def test_mentor_spec_mentions_holding_horizon(self):
        spec = load_persona_spec("mentor")
        assert "시계" in spec or "보유 기간" in spec or "년 보유" in spec

    def test_mentor_spec_mentions_life_stage(self):
        spec = load_persona_spec("mentor")
        for stage in ["자산 형성기", "자산 확장기", "자산 보존기"]:
            assert stage in spec, f"mentor.md에 생애주기 '{stage}' 매핑 누락"

    def test_cfo_spec_uses_profile_for_inputs(self):
        spec = load_persona_spec("practitioner")
        assert "프로필" in spec, "practitioner.md에 프로필 활용 가이드 누락"
        assert "예산" in spec, "practitioner.md에 budget_manwon 활용 가이드 누락"
        assert "주택" in spec, "practitioner.md에 property_count 활용 가이드 누락"

    def test_cso_spec_uses_profile_for_critique(self):
        spec = load_persona_spec("redteam")
        assert "프로필" in spec or "프로파일" in spec, \
            "redteam.md에 프로필/프로파일 활용 가이드 누락"

    def test_cfo_spec_still_forbids_suitability_advice(self):
        """프로필 활용 추가 후에도 CFO의 영역 경계가 살아있어야 함."""
        spec = load_persona_spec("practitioner")
        assert "투자컨설턴트" in spec or "적합성" in spec

    def test_cso_spec_still_forbids_suitability_advice(self):
        """프로필 활용 추가 후에도 CSO의 영역 경계가 살아있어야 함."""
        spec = load_persona_spec("redteam")
        assert "투자컨설턴트" in spec or "적합성" in spec

    def test_diversity_angles_include_profile_for_mentor(self):
        from personas import DIVERSITY_ANGLES
        assert "프로필반영" in DIVERSITY_ANGLES["mentor"], \
            "mentor의 다양성 각도에 '프로필반영' 추가 누락"

    def test_system_prompt_for_mentor_contains_profile_guidance(self):
        """build_system_prompt가 페르소나 명세에서 프로필 섹션을 그대로 포함하는지."""
        prompt = build_system_prompt("mentor")
        assert "프로필" in prompt
