"""Tests for profiles module (Phase A.1)."""
from profiles import (
    INVESTMENT_GOALS,
    LIFE_STAGES,
    RISK_PROFILES,
    Profile,
    delete_profile,
    format_for_agents,
    list_profiles,
    load_profile,
    save_profile,
)


class TestProfileDataclass:
    def test_default_profile_is_valid(self):
        p = Profile()
        assert p.nickname == "대표님"
        assert p.risk_profile in RISK_PROFILES
        assert p.investment_goal in INVESTMENT_GOALS
        assert p.life_stage in LIFE_STAGES
        assert p.budget_manwon == 0
        assert p.property_count == 1
        assert p.holding_years == 5

    def test_labels_translate_to_korean(self):
        p = Profile(
            risk_profile="conservative",
            investment_goal="capital_gain",
            life_stage="preservation",
        )
        assert p.risk_label == "보수적"
        assert p.goal_label == "시세차익형"
        assert p.life_stage_label == "자산 보존기"

    def test_to_dict_from_dict_roundtrip(self):
        p = Profile(nickname="홍길동", budget_manwon=45000, notes="테스트")
        d = p.to_dict()
        p2 = Profile.from_dict(d)
        assert p == p2

    def test_from_dict_ignores_unknown_keys(self):
        d = {"nickname": "X", "unknown_field": "ignored"}
        p = Profile.from_dict(d)
        assert p.nickname == "X"

    def test_unknown_enum_value_falls_back_to_raw(self):
        p = Profile(risk_profile="custom_X")
        assert p.risk_label == "custom_X"


class TestPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        p = Profile(nickname="홍대표", budget_manwon=50000, notes="강남 우선")
        path = save_profile(p, "test_user", profiles_dir=tmp_path)
        assert path.exists()
        loaded = load_profile("test_user", profiles_dir=tmp_path)
        assert loaded == p

    def test_load_missing_returns_none(self, tmp_path):
        assert load_profile("nonexistent", profiles_dir=tmp_path) is None

    def test_list_profiles_empty_dir(self, tmp_path):
        assert list_profiles(profiles_dir=tmp_path) == []

    def test_list_profiles_sorted(self, tmp_path):
        save_profile(Profile(), "zebra", profiles_dir=tmp_path)
        save_profile(Profile(), "apple", profiles_dir=tmp_path)
        save_profile(Profile(), "mango", profiles_dir=tmp_path)
        assert list_profiles(profiles_dir=tmp_path) == ["apple", "mango", "zebra"]

    def test_delete_profile(self, tmp_path):
        save_profile(Profile(), "tmp", profiles_dir=tmp_path)
        assert delete_profile("tmp", profiles_dir=tmp_path)
        assert load_profile("tmp", profiles_dir=tmp_path) is None

    def test_delete_nonexistent(self, tmp_path):
        assert not delete_profile("nope", profiles_dir=tmp_path)

    def test_save_creates_directory(self, tmp_path):
        nested = tmp_path / "nested" / "profiles"
        save_profile(Profile(), "x", profiles_dir=nested)
        assert nested.exists()

    def test_save_writes_utf8_korean(self, tmp_path):
        p = Profile(notes="강남구 우선")
        path = save_profile(p, "kr", profiles_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "강남구 우선" in content


class TestFormatForAgents:
    def test_none_returns_empty(self):
        assert format_for_agents(None) == ""

    def test_includes_key_info(self):
        p = Profile(
            nickname="홍대표",
            risk_profile="aggressive",
            investment_goal="rental",
            budget_manwon=45000,
            property_count=2,
            holding_years=7,
            life_stage="expansion",
            notes="강남 우선 검토",
        )
        text = format_for_agents(p)
        assert "홍대표" in text
        assert "공격적" in text
        assert "월세 수익형" in text
        assert "4억 5,000만원" in text
        assert "2주택" in text
        assert "7년 보유" in text
        assert "자산 확장기" in text
        assert "강남 우선 검토" in text

    def test_zero_budget_renders_as_미입력(self):
        p = Profile(budget_manwon=0)
        assert "미입력" in format_for_agents(p)

    def test_round_eok_budget(self):
        p = Profile(budget_manwon=30000)
        assert "3억원" in format_for_agents(p)

    def test_no_house_label(self):
        p = Profile(property_count=0)
        assert "무주택" in format_for_agents(p)

    def test_three_or_more_houses_marked_multi(self):
        p = Profile(property_count=4)
        text = format_for_agents(p)
        assert "다주택자" in text

    def test_notes_omitted_when_empty(self):
        p = Profile(notes="")
        text = format_for_agents(p)
        assert "메모:" not in text

    def test_block_targets_consultant(self):
        p = Profile()
        text = format_for_agents(p)
        assert "투자컨설턴트" in text
        assert "프로필" in text
