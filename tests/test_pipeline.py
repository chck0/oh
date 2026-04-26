"""Tests for the shared data pipeline."""
from pipeline import PipelineResult, run_pipeline


class TestPipelineResult:
    def test_default_empty(self):
        r = PipelineResult()
        assert r.summaries == []
        assert r.analyses == []
        assert r.market_text == ""
        assert r.all_data_text == ""

    def test_all_data_text_joins(self):
        r = PipelineResult(market_text="A", yield_text="B", score_text="C")
        text = r.all_data_text
        assert "A" in text
        assert "B" in text
        assert "C" in text


class TestRunPipeline:
    def test_returns_pipeline_result(self):
        r = run_pipeline(["강남구"])
        assert isinstance(r, PipelineResult)
        assert len(r.summaries) > 0
        assert r.market_text != ""

    def test_analyses_populated(self):
        r = run_pipeline(["강남구"])
        assert len(r.analyses) > 0
        assert r.yield_text != ""

    def test_cashflow_populated(self):
        r = run_pipeline(["강남구"])
        assert len(r.cf_tables) > 0
        assert r.cashflow_text != ""

    def test_monte_carlo_populated(self):
        r = run_pipeline(["강남구"])
        assert len(r.mc_results) > 0
        assert r.mc_text != ""

    def test_tax_populated(self):
        r = run_pipeline(["강남구"])
        assert len(r.tax_summaries) > 0
        assert r.tax_text != ""

    def test_scorecard_populated(self):
        r = run_pipeline(["강남구"])
        assert len(r.scorecards) > 0
        assert r.score_text != ""

    def test_portfolio_needs_two_regions(self):
        r = run_pipeline(["강남구"])
        assert r.portfolios == []
        assert r.port_text == ""

    def test_portfolio_with_two_regions(self):
        r = run_pipeline(["강남구", "성동구"])
        assert len(r.portfolios) > 0
        assert r.port_text != ""

    def test_flags_disable_steps(self):
        r = run_pipeline(
            ["강남구"],
            use_cashflow=False,
            use_monte_carlo=False,
            use_tax=False,
            use_scorecard=False,
        )
        assert r.cf_tables == []
        assert r.mc_results == []
        assert r.tax_summaries == []
        assert r.scorecards == []
        assert r.market_text != ""
        assert r.yield_text != ""

    def test_all_data_text_property(self):
        r = run_pipeline(["강남구"])
        text = r.all_data_text
        assert r.market_text in text
        assert r.yield_text in text
