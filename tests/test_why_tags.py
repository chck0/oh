"""
scripts/tag_price_reason.py 순수 함수 단위 테스트

- calc_floor_tag    : 층수 → 태그 라벨
- calc_price_chg_tag: 직전 거래 대비 변동률 → 태그 라벨
- _months_between   : 두 연월 사이 개월 수
"""
import pytest
from scripts.tag_price_reason import (
    calc_floor_tag,
    calc_price_chg_tag,
    _months_between,
)


# ── calc_floor_tag ────────────────────────────────────────────

class TestCalcFloorTag:
    def test_floor_1_returns_label(self):
        tag = calc_floor_tag(1, 20)
        assert tag is not None
        assert tag['label'] == '1층 매물'

    def test_floor_1_ignores_ratio(self):
        """1층은 비율이 아무리 낮아도 '1층 매물' (비율보다 우선)."""
        tag = calc_floor_tag(1, 100)
        assert tag['label'] == '1층 매물'

    def test_floor_0_returns_none(self):
        assert calc_floor_tag(0, 20) is None

    def test_floor_none_returns_none(self):
        assert calc_floor_tag(None, 20) is None

    def test_top_floor_none_returns_none(self):
        """1층 제외, top_floor 없으면 비율 계산 불가 → None."""
        assert calc_floor_tag(5, None) is None

    def test_top_floor_zero_returns_none(self):
        assert calc_floor_tag(3, 0) is None

    def test_ratio_le_015_returns_저층(self):
        # floor=3, top=25 → ratio=0.12 ≤ 0.15
        tag = calc_floor_tag(3, 25)
        assert tag is not None
        assert tag['label'] == '저층 매물'
        assert tag['type'] == 'floor'

    def test_ratio_le_030_returns_1층대(self):
        # floor=5, top=25 → ratio=0.20, 0.15 < 0.20 ≤ 0.30
        tag = calc_floor_tag(5, 25)
        assert tag is not None
        assert tag['label'] == '1층대 매물'

    def test_ratio_middle_returns_none(self):
        # floor=12, top=25 → ratio=0.48, 중간층
        assert calc_floor_tag(12, 25) is None

    def test_ratio_ge_085_returns_고층(self):
        # floor=22, top=25 → ratio=0.88 ≥ 0.85
        tag = calc_floor_tag(22, 25)
        assert tag is not None
        assert tag['label'] == '고층 매물'

    def test_tag_has_detail_for_nonone(self):
        """1층이 아닌 태그는 detail에 층수 정보 포함."""
        tag = calc_floor_tag(3, 25)
        assert tag['detail'] is not None
        assert '25층' in tag['detail']
        assert '3층' in tag['detail']

    def test_floor_1_detail_is_none(self):
        """1층 태그는 detail 없음."""
        tag = calc_floor_tag(1, 20)
        assert tag['detail'] is None


# ── calc_price_chg_tag ────────────────────────────────────────

class TestCalcPriceChgTag:
    def test_prev_none_returns_none(self):
        assert calc_price_chg_tag(50000, None, 3) is None

    def test_prev_zero_returns_none(self):
        assert calc_price_chg_tag(50000, 0, 3) is None

    def test_curr_none_returns_none(self):
        assert calc_price_chg_tag(None, 50000, 3) is None

    def test_months_gap_gt_6_returns_none(self):
        assert calc_price_chg_tag(50000, 60000, 7) is None

    def test_months_gap_none_returns_none(self):
        assert calc_price_chg_tag(50000, 60000, None) is None

    def test_small_drop_below_5pct_returns_none(self):
        # 변동률 -3% → 임계값 미만
        assert calc_price_chg_tag(48500, 50000, 2) is None

    def test_large_drop_returns_price_chg_tag(self):
        # 변동률 -10%
        tag = calc_price_chg_tag(45000, 50000, 3)
        assert tag is not None
        assert tag['type'] == 'price_chg'
        assert '-' in tag['label']

    def test_large_rise_returns_price_chg_tag(self):
        # 변동률 +10%
        tag = calc_price_chg_tag(55000, 50000, 2)
        assert tag is not None
        assert '상승' in tag['label']

    def test_exactly_5pct_drop_returns_tag(self):
        # 변동률 정확히 -5%
        tag = calc_price_chg_tag(47500, 50000, 1)
        assert tag is not None

    def test_exactly_5pct_rise_returns_tag(self):
        # 변동률 정확히 +5%
        tag = calc_price_chg_tag(52500, 50000, 1)
        assert tag is not None

    def test_zero_change_returns_none(self):
        assert calc_price_chg_tag(50000, 50000, 2) is None

    def test_months_gap_exactly_6_allowed(self):
        """6개월 이내 기준 — 정확히 6개월은 허용."""
        tag = calc_price_chg_tag(45000, 50000, 6)
        assert tag is not None

    def test_detail_contains_pct(self):
        tag = calc_price_chg_tag(45000, 50000, 3)
        assert tag['detail'] is not None
        assert '%' in tag['detail']


# ── _months_between ───────────────────────────────────────────

class TestMonthsBetween:
    def test_same_month_is_zero(self):
        assert _months_between(2026, 3, 2026, 3) == 0

    def test_one_month_gap(self):
        assert _months_between(2026, 3, 2026, 4) == 1

    def test_cross_year(self):
        assert _months_between(2025, 11, 2026, 2) == 3

    def test_full_year(self):
        assert _months_between(2025, 1, 2026, 1) == 12

    def test_negative_when_reversed(self):
        """두 번째 날짜가 더 이른 경우 음수."""
        assert _months_between(2026, 5, 2026, 3) == -2
