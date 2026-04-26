"""Tests for the user manual module."""
from manual import MANUAL_TEXT, FILE_SAMPLE_TEXT


class TestManualText:
    def test_not_empty(self):
        assert len(MANUAL_TEXT) > 100

    def test_has_title(self):
        assert "사용 매뉴얼" in MANUAL_TEXT

    def test_has_quick_start(self):
        assert "빠른 시작" in MANUAL_TEXT

    def test_has_file_upload_guide(self):
        assert "파일 업로드 가이드" in MANUAL_TEXT

    def test_has_yield_explanation(self):
        assert "표면수익률" in MANUAL_TEXT
        assert "순수익률" in MANUAL_TEXT
        assert "레버리지" in MANUAL_TEXT

    def test_has_scenario_explanation(self):
        assert "시나리오" in MANUAL_TEXT
        assert "스트레스 테스트" in MANUAL_TEXT

    def test_has_cashflow_explanation(self):
        assert "현금흐름" in MANUAL_TEXT
        assert "IRR" in MANUAL_TEXT
        assert "NPV" in MANUAL_TEXT

    def test_has_monte_carlo_explanation(self):
        assert "Monte Carlo" in MANUAL_TEXT
        assert "손실확률" in MANUAL_TEXT

    def test_has_tax_explanation(self):
        assert "취득세" in MANUAL_TEXT
        assert "보유세" in MANUAL_TEXT
        assert "양도세" in MANUAL_TEXT

    def test_has_scorecard_explanation(self):
        assert "스코어카드" in MANUAL_TEXT
        assert "100점" in MANUAL_TEXT
        assert "투자 추천" in MANUAL_TEXT

    def test_has_portfolio_explanation(self):
        assert "포트폴리오" in MANUAL_TEXT

    def test_has_faq(self):
        assert "자주 묻는 질문" in MANUAL_TEXT

    def test_has_agent_roles(self):
        assert "CFO" in MANUAL_TEXT
        assert "CSO" in MANUAL_TEXT
        assert "투자컨설턴트" in MANUAL_TEXT


class TestFileSampleText:
    def test_not_empty(self):
        assert len(FILE_SAMPLE_TEXT) > 50

    def test_has_excel_sample(self):
        assert "Excel" in FILE_SAMPLE_TEXT
        assert "매물 비교표" in FILE_SAMPLE_TEXT

    def test_has_columns(self):
        assert "매매가" in FILE_SAMPLE_TEXT
        assert "월세" in FILE_SAMPLE_TEXT
        assert "면적" in FILE_SAMPLE_TEXT
