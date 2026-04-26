"""Shared fixtures for the test suite."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from real_estate import get_multi_region_data, RegionSummary
from yield_analyzer import InvestmentParams


@pytest.fixture
def sample_summaries() -> list[RegionSummary]:
    return get_multi_region_data(["강남구", "성동구", "강서구"])


@pytest.fixture
def gangnam_summary(sample_summaries) -> RegionSummary:
    return sample_summaries[0]


@pytest.fixture
def default_params() -> InvestmentParams:
    return InvestmentParams()
