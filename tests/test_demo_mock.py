"""Tests for demo_mock module — Gold Standard mock demo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from demo_mock import MOCK_TURNS, MOCK_MINUTES, DEMO_TOPIC, DEMO_REGIONS


class TestMockData:
    def test_demo_topic(self):
        assert "강남" in DEMO_TOPIC

    def test_demo_regions(self):
        assert len(DEMO_REGIONS) == 3
        assert "강남구" in DEMO_REGIONS

    def test_mock_turns_count(self):
        assert len(MOCK_TURNS) == 3

    def test_each_turn_has_all_agents(self):
        for i, turn in enumerate(MOCK_TURNS):
            assert "user" in turn, f"Turn {i}: missing user"
            assert "practitioner" in turn, f"Turn {i}: missing practitioner"
            assert "redteam" in turn, f"Turn {i}: missing redteam"
            assert "mentor" in turn, f"Turn {i}: missing mentor"

    def test_cfo_cites_sources(self):
        for turn in MOCK_TURNS:
            assert "[출처:" in turn["practitioner"], \
                "CFO(practitioner) 응답에 출처 인용이 없습니다"

    def test_cso_raises_risk(self):
        risk_keywords = ["리스크", "위험", "불리", "압력", "마이너스", "안 맞",
                         "빠진", "규제", "의존", "급등"]
        for turn in MOCK_TURNS:
            has_risk = any(kw in turn["redteam"] for kw in risk_keywords)
            assert has_risk, "CSO(redteam) 응답에 리스크/반론이 없습니다"

    def test_mentor_provides_advisory(self):
        advisory_keywords = ["적합", "분산", "포트폴리오", "권역", "리스크",
                             "기준", "유리", "권합니다", "조합", "성향"]
        for turn in MOCK_TURNS:
            has_advisory = any(kw in turn["mentor"] for kw in advisory_keywords)
            assert has_advisory, "투자컨설턴트(mentor) 응답에 자문 의견이 없습니다"


class TestMockMinutes:
    def test_has_template_placeholder(self):
        assert "{timestamp}" in MOCK_MINUTES

    def test_has_required_sections(self):
        formatted = MOCK_MINUTES.format(timestamp="2026-04-17 14:00")
        assert "핵심 안건" in formatted
        assert "주요 논의" in formatted
        assert "결정사항" in formatted
        assert "보류사항" in formatted
        assert "Next Action" in formatted

    def test_has_action_items(self):
        formatted = MOCK_MINUTES.format(timestamp="2026-04-17 14:00")
        assert "담당:" in formatted
        assert "기한:" in formatted


class TestMockDemoCLI:
    def test_main_runs(self, capsys):
        from demo_mock import main
        main()
        captured = capsys.readouterr()
        assert "Mock Demo" in captured.out
        assert "강남구" in captured.out
        assert "수익률" in captured.out
        assert "시나리오" in captured.out or "민감도" in captured.out
        assert "회의록" in captured.out


class TestProfileAwareness:
    """Phase A.4 — Gold Standard mentor 응답이 사용자 프로필 어휘를 자연스럽게 인용하는지 검증."""

    def test_mentor_uses_risk_profile_vocab(self):
        """전체 turn 중 적어도 한 곳에는 리스크 프로파일 어휘가 등장해야 한다."""
        risk_keywords = ["보수적", "공격적", "성향", "프로파일", "프로필"]
        found = [
            i for i, t in enumerate(MOCK_TURNS)
            if any(kw in t["mentor"] for kw in risk_keywords)
        ]
        assert found, "Mentor 응답에 리스크 프로파일 어휘가 한 군데도 없습니다"

    def test_mentor_references_investment_goal_types(self):
        """월세형 vs 시세차익형 같은 투자 목적 어휘가 등장해야 한다."""
        goal_keywords = ["월세", "시세차익", "시세 차익", "수익형"]
        joined = " ".join(t["mentor"] for t in MOCK_TURNS)
        assert any(kw in joined for kw in goal_keywords), \
            "Mentor 응답에 투자 목적 어휘가 없습니다"

    def test_mentor_anchors_to_client_situation(self):
        """최소 2개 turn에서 클라이언트 컨텍스트 어휘를 명시 인용해야 한다."""
        anchor_keywords = ["대표님", "상황", "성향", "목적", "기준"]
        matching = [
            i for i, t in enumerate(MOCK_TURNS)
            if sum(1 for kw in anchor_keywords if kw in t["mentor"]) >= 2
        ]
        assert len(matching) >= 2, \
            f"Mentor가 '대표님 상황' 류 자문을 거의 안 합니다 (matching={matching})"

    def test_mentor_does_not_compute_numbers(self):
        """프로필 활용해도 mentor가 계산을 하면 안 된다 (영역 경계)."""
        # 출처 표기 패턴([출처: ...])이 mentor 응답에 등장하면 CFO 영역 침범 의심
        for i, t in enumerate(MOCK_TURNS):
            assert "[출처:" not in t["mentor"], \
                f"Turn {i} mentor 응답에 [출처: ...] 인용이 들어감 — CFO 영역 침범"
