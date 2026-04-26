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
