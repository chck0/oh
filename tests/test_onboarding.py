"""온보딩 모듈 테스트.

순수 함수 위주의 단위 테스트. Streamlit 의존성 없이 답변 → Profile/topic
매핑이 결정적으로 작동하는지 검증한다.
"""
from onboarding import (
    ONBOARDING_STEPS,
    OnboardingAnswers,
    build_checklist,
    build_profile,
    build_questions_for_agent,
    build_topic,
)
from profiles import INVESTMENT_GOALS, RISK_PROFILES


class TestOnboardingSpec:
    def test_three_steps_exposed(self):
        ids = [s["id"] for s in ONBOARDING_STEPS]
        assert ids == ["purpose", "budget", "loan_ratio"]

    def test_each_step_has_options_dict(self):
        for spec in ONBOARDING_STEPS:
            assert "question" in spec
            assert isinstance(spec["options"], dict)
            assert len(spec["options"]) >= 2


class TestOnboardingAnswers:
    def test_default_is_incomplete(self):
        assert not OnboardingAnswers().is_complete()

    def test_full_answer_is_complete(self):
        a = OnboardingAnswers(purpose="residence", budget_manwon=40000, loan_ratio="medium")
        assert a.is_complete()

    def test_zero_budget_is_incomplete(self):
        a = OnboardingAnswers(purpose="rental", budget_manwon=0, loan_ratio="low")
        assert not a.is_complete()


class TestBuildProfile:
    def test_residence_maps_to_mixed_goal(self):
        a = OnboardingAnswers(purpose="residence", budget_manwon=40000, loan_ratio="low")
        p = build_profile(a)
        assert p.investment_goal == "mixed"
        assert p.nickname == "첫 구매자"

    def test_rental_maps_to_rental_goal(self):
        a = OnboardingAnswers(purpose="rental", budget_manwon=60000, loan_ratio="medium")
        p = build_profile(a)
        assert p.investment_goal == "rental"
        assert p.nickname == "투자 입문자"

    def test_high_loan_implies_aggressive_risk(self):
        a = OnboardingAnswers(purpose="capital_gain", budget_manwon=85000, loan_ratio="high")
        assert build_profile(a).risk_profile == "aggressive"

    def test_no_loan_implies_conservative_risk(self):
        a = OnboardingAnswers(purpose="residence", budget_manwon=25000, loan_ratio="none")
        assert build_profile(a).risk_profile == "conservative"

    def test_unknown_loan_defaults_to_moderate(self):
        a = OnboardingAnswers(purpose="rental", budget_manwon=40000, loan_ratio="unknown")
        assert build_profile(a).risk_profile == "moderate"

    def test_first_time_buyer_property_count_is_zero(self):
        a = OnboardingAnswers(purpose="residence", budget_manwon=40000, loan_ratio="medium")
        assert build_profile(a).property_count == 0

    def test_residence_has_longer_horizon_than_investment(self):
        residence = build_profile(OnboardingAnswers("residence", 40000, "low"))
        investment = build_profile(OnboardingAnswers("rental", 40000, "low"))
        assert residence.holding_years > investment.holding_years

    def test_profile_outputs_known_label_keys(self):
        a = OnboardingAnswers(purpose="mixed", budget_manwon=60000, loan_ratio="medium")
        p = build_profile(a)
        assert p.investment_goal in INVESTMENT_GOALS
        assert p.risk_profile in RISK_PROFILES

    def test_notes_mention_first_time_buyer_context(self):
        a = OnboardingAnswers(purpose="residence", budget_manwon=40000, loan_ratio="medium")
        notes = build_profile(a).notes
        assert "첫" in notes or "처음" in notes
        assert "체크포인트" in notes or "공인중개사" in notes


class TestBuildTopic:
    def test_topic_includes_budget_in_okay_format(self):
        topic = build_topic(OnboardingAnswers("residence", 40000, "low"))
        assert "4억" in topic

    def test_topic_under_one_billion_uses_manwon(self):
        topic = build_topic(OnboardingAnswers("residence", 8000, "low"))
        assert "8000만원" in topic

    def test_topic_purpose_phrase_differs_by_purpose(self):
        residence = build_topic(OnboardingAnswers("residence", 40000, "low"))
        rental = build_topic(OnboardingAnswers("rental", 40000, "low"))
        assert residence != rental


class TestBuildChecklist:
    def test_baseline_checklist_has_core_items(self):
        items = build_checklist(OnboardingAnswers("residence", 40000, "low"))
        joined = "\n".join(items)
        assert "관리비" in joined
        assert "전용률" in joined
        assert "취득세" in joined

    def test_high_loan_adds_dsr_and_rate_simulation(self):
        items = build_checklist(OnboardingAnswers("rental", 60000, "high"))
        joined = "\n".join(items)
        assert "DSR" in joined or "LTV" in joined
        assert "금리" in joined

    def test_rental_adds_rent_trend_item(self):
        items = build_checklist(OnboardingAnswers("rental", 60000, "low"))
        assert any("임대료" in it for it in items)

    def test_capital_gain_adds_price_trend_item(self):
        items = build_checklist(OnboardingAnswers("capital_gain", 85000, "low"))
        assert any("실거래가" in it for it in items)


class TestBuildQuestionsForAgent:
    def test_baseline_three_questions(self):
        qs = build_questions_for_agent(OnboardingAnswers("residence", 40000, "low"))
        assert len(qs) >= 3

    def test_residence_includes_school_question(self):
        qs = build_questions_for_agent(OnboardingAnswers("residence", 40000, "low"))
        assert any("초등학교" in q or "생활권" in q for q in qs)

    def test_rental_includes_rent_question(self):
        qs = build_questions_for_agent(OnboardingAnswers("rental", 60000, "low"))
        assert any("임대" in q for q in qs)
