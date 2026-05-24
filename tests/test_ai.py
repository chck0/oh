"""
app/ai.py 순수 함수 테스트 (LLM 호출 없음)

- make_buckets, bucket_label, assign_bucket : 통근 버킷 로직
- card_key                                  : 카드 고유 키 생성
- build_recommendations                     : 버킷×평형 매트릭스 추천
- build_stats                               : 검색 결과 통계
- _fmt_price                               : 가격 포맷팅
"""
from datetime import date
import pytest
from app.ai import (
    make_buckets,
    bucket_label,
    assign_bucket,
    card_key,
    build_recommendations,
    build_stats,
    _fmt_price,
    _make_pick_reason,
    _make_prompt_recommend,
    _make_prompt_regular,
)


# ── 테스트 픽스처 헬퍼 ──────────────────────────────────────

def _card(apt_seq, pyeong_type, price_low, total_time_min, build_year=2015):
    """기본 카드 dict 생성"""
    return {
        'apt_seq': apt_seq,
        'pyeong_type': pyeong_type,
        'price_low': price_low,
        'total_time_min': total_time_min,
        'apt_nm': f'테스트아파트{apt_seq}',
        'umd_nm': '테스트동',
        'build_year': build_year,
        'bus_cnt': 0,
        'subway_cnt': 1,
        'deal_count': 5,
        'transit_summary': '2호선 직통',
        'kaptdaCnt': 300,
        'top_floor': 15,
    }


# ── make_buckets ──────────────────────────────────────────────

class TestMakeBuckets:
    def test_exactly_30_minutes(self):
        bs = make_buckets(30)
        assert bs == [(0, 30)]

    def test_60_minutes_generates_4_buckets(self):
        bs = make_buckets(60)
        assert bs == [(0, 30), (30, 40), (40, 50), (50, 60)]

    def test_last_bucket_ends_at_max(self):
        bs = make_buckets(45)
        assert bs[-1][1] == 45

    def test_buckets_are_contiguous(self):
        bs = make_buckets(60)
        for i in range(len(bs) - 1):
            assert bs[i][1] == bs[i + 1][0], "버킷 사이 간격 없어야 함"

    def test_starts_from_zero(self):
        bs = make_buckets(60)
        assert bs[0][0] == 0

    def test_non_multiple_of_10(self):
        bs = make_buckets(55)
        assert bs[-1][1] == 55


# ── bucket_label ──────────────────────────────────────────────

class TestBucketLabel:
    def test_zero_start_shows_N분_이내(self):
        assert bucket_label(0, 30) == '30분 이내'

    def test_nonzero_start_shows_range(self):
        assert bucket_label(30, 40) == '30~40분'
        assert bucket_label(40, 50) == '40~50분'

    def test_last_bucket_format(self):
        assert bucket_label(50, 60) == '50~60분'


# ── assign_bucket ─────────────────────────────────────────────

class TestAssignBucket:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.bs = make_buckets(60)  # [(0,30),(30,40),(40,50),(50,60)]

    def test_zero_goes_to_first_bucket(self):
        assert assign_bucket(0, self.bs) == 0

    def test_at_first_boundary(self):
        assert assign_bucket(30, self.bs) == 0

    def test_just_over_first_boundary(self):
        assert assign_bucket(31, self.bs) == 1

    def test_exactly_at_second_boundary(self):
        assert assign_bucket(40, self.bs) == 1

    def test_third_bucket(self):
        assert assign_bucket(45, self.bs) == 2

    def test_last_bucket_boundary(self):
        assert assign_bucket(60, self.bs) == 3

    def test_over_max_goes_to_last(self):
        assert assign_bucket(999, self.bs) == len(self.bs) - 1


# ── card_key ──────────────────────────────────────────────────

class TestCardKey:
    def test_basic(self):
        c = {'apt_seq': 'A001', 'pyeong_type': '20평대'}
        assert card_key(c) == 'A001:20평대'

    def test_missing_pyeong_type_defaults_to_empty(self):
        c = {'apt_seq': 'B002'}
        assert card_key(c) == 'B002:'

    def test_unique_per_pyeong_type(self):
        c1 = {'apt_seq': 'A001', 'pyeong_type': '20평대'}
        c2 = {'apt_seq': 'A001', 'pyeong_type': '30평대'}
        assert card_key(c1) != card_key(c2)


# ── _fmt_price ────────────────────────────────────────────────

class TestFmtPrice:
    def test_zero_returns_dash(self):
        assert _fmt_price(0) == '-'

    def test_none_returns_dash(self):
        assert _fmt_price(None) == '-'  # type: ignore[arg-type]

    def test_exact_1억(self):
        assert _fmt_price(10_000) == '1억'

    def test_1억_5천(self):
        assert _fmt_price(15_000) == '1억 5천'

    def test_5억(self):
        assert _fmt_price(50_000) == '5억'

    def test_5억_3천(self):
        assert _fmt_price(53_000) == '5억 3천'

    def test_10억(self):
        assert _fmt_price(100_000) == '10억'

    def test_no_trailing_천_if_zero(self):
        result = _fmt_price(20_000)
        assert '천' not in result


# ── build_recommendations ─────────────────────────────────────

class TestBuildRecommendations:
    def test_empty_cards_returns_empty(self):
        result = build_recommendations([], 60)
        assert result == {'buckets': [], 'cards': []}

    def test_single_card_is_recommended(self):
        cards = [_card('A001', '20평대', 30_000, 20)]
        result = build_recommendations(cards, 60)
        assert result['cards'][0]['is_recommended'] is True

    def test_buckets_generated(self):
        cards = [_card('A001', '20평대', 30_000, 20)]
        result = build_recommendations(cards, 60)
        assert len(result['buckets']) == 4

    def test_cheapest_per_slot_is_recommended(self):
        cards = [
            _card('A001', '20평대', 35_000, 20),  # 비쌈
            _card('A002', '20평대', 28_000, 25),  # 같은 버킷, 저렴
        ]
        result = build_recommendations(cards, 60)
        rec = [c for c in result['cards'] if c['is_recommended']]
        assert len(rec) == 1
        assert rec[0]['apt_seq'] == 'A002'

    def test_different_pyeong_types_get_separate_picks(self):
        cards = [
            _card('A001', '20평대', 30_000, 20),
            _card('A002', '30평대', 50_000, 20),
        ]
        result = build_recommendations(cards, 60)
        rec = [c for c in result['cards'] if c['is_recommended']]
        assert len(rec) == 2

    def test_same_apt_seq_recommended_at_most_once(self):
        cards = [
            _card('A001', '20평대', 30_000, 20),
            {**_card('A001', '30평대', 50_000, 20)},  # 같은 단지, 다른 평형
        ]
        result = build_recommendations(cards, 60)
        rec = [c for c in result['cards'] if c['is_recommended']]
        assert len(rec) == 1

    def test_bucket_label_assigned(self):
        cards = [_card('A001', '20평대', 30_000, 20)]
        result = build_recommendations(cards, 60)
        assert result['cards'][0]['bucket_label'] == '30분 이내'

    def test_non_recommended_flag_set_to_false(self):
        cards = [
            _card('A001', '20평대', 28_000, 20),  # 추천됨
            _card('A002', '20평대', 35_000, 25),  # 같은 버킷, 더 비쌈 → 미추천
        ]
        result = build_recommendations(cards, 60)
        a002 = next(c for c in result['cards'] if c['apt_seq'] == 'A002')
        assert a002['is_recommended'] is False

    def test_price_diff_vs_fastest_is_zero_for_baseline(self):
        # 최단 버킷의 최저가 카드 → diff=0
        cards = [_card('A001', '20평대', 30_000, 20)]
        result = build_recommendations(cards, 60)
        rec = result['cards'][0]
        assert rec['price_diff_vs_fastest'] == 0

    def test_pick_reason_is_string(self):
        cards = [_card('A001', '20평대', 30_000, 20)]
        result = build_recommendations(cards, 60)
        assert isinstance(result['cards'][0]['pick_reason'], str)
        assert len(result['cards'][0]['pick_reason']) > 0

    def test_bucket_idx_assigned(self):
        cards = [
            _card('A001', '20평대', 30_000, 20),   # bucket 0 (≤30분)
            _card('A002', '20평대', 32_000, 35),   # bucket 1 (30~40분)
        ]
        result = build_recommendations(cards, 60)
        by_seq = {c['apt_seq']: c for c in result['cards']}
        assert by_seq['A001']['bucket_idx'] == 0
        assert by_seq['A002']['bucket_idx'] == 1


# ── build_stats ───────────────────────────────────────────────

class TestBuildStats:
    @pytest.fixture(autouse=True)
    def setup(self):
        raw = [
            _card('A001', '20평대', 30_000, 20, build_year=2015),
            _card('A002', '30평대', 50_000, 35, build_year=2015),
            _card('A003', '20평대', 32_000, 45, build_year=2000),
        ]
        result = build_recommendations(raw, 60)
        self.cards = result['cards']
        self.buckets = result['buckets']

    def test_empty_returns_total_zero(self):
        assert build_stats([], []) == {'total': 0}

    def test_total_count(self):
        stats = build_stats(self.cards, self.buckets)
        assert stats['total'] == 3

    def test_avg_price(self):
        stats = build_stats(self.cards, self.buckets)
        expected = (30_000 + 50_000 + 32_000) // 3
        assert stats['avg_price'] == expected

    def test_commute_curve_non_empty(self):
        stats = build_stats(self.cards, self.buckets)
        assert len(stats['commute_curve']) > 0

    def test_commute_curve_has_required_keys(self):
        stats = build_stats(self.cards, self.buckets)
        entry = stats['commute_curve'][0]
        assert 'label' in entry
        assert 'avg_price' in entry
        assert 'count' in entry

    def test_pyeong_breakdown_contains_both_types(self):
        stats = build_stats(self.cards, self.buckets)
        pts = {p['pyeong_type'] for p in stats['pyeong_breakdown']}
        assert '20평대' in pts
        assert '30평대' in pts

    def test_age_breakdown_sum_matches_total(self):
        stats = build_stats(self.cards, self.buckets)
        ab = stats['age_breakdown']
        total_age = ab['new_10'] + ab['mid_20'] + ab['old'] + ab['unknown']
        assert total_age == stats['total']

    def test_age_breakdown_keys_exist(self):
        stats = build_stats(self.cards, self.buckets)
        ab = stats['age_breakdown']
        assert set(ab.keys()) == {'new_10', 'mid_20', 'old', 'unknown'}

    def test_unknown_build_year_counted(self):
        raw = [_card('X001', '20평대', 30_000, 20, build_year=None)]
        # build_year=None → build_year 키를 None으로 설정
        raw[0]['build_year'] = None
        result = build_recommendations(raw, 60)
        stats = build_stats(result['cards'], result['buckets'])
        assert stats['age_breakdown']['unknown'] == 1


# ── _make_pick_reason ─────────────────────────────────────────

class TestMakePickReason:
    def _card_with_diff(self, diff: int, bucket_label='0-30분', pt='20평대'):
        return {
            'bucket_label': bucket_label,
            'pyeong_type': pt,
            'price_diff_vs_fastest': diff,
        }

    def test_diff_zero_mentions_slot_min(self):
        """diff=0 → 최단버킷 슬롯 최저가 문구"""
        reason = _make_pick_reason(self._card_with_diff(0), [{}], None)
        assert '최저가' in reason
        assert '0-30분' in reason

    def test_diff_positive_mentions_cheaper(self):
        """diff>0 → 최단버킷보다 N억 저렴 문구"""
        reason = _make_pick_reason(self._card_with_diff(10_000), [{}] * 3, None)
        assert '저렴' in reason

    def test_diff_negative_mentions_slot(self):
        """diff<0 → 슬롯 최저가 문구 (거의 발생 안 하지만 브랜치 커버)"""
        reason = _make_pick_reason(self._card_with_diff(-5_000), [{}], None)
        assert '최저가' in reason

    def test_slot_size_reflected_in_reason(self):
        slot_items = [{}] * 5
        reason = _make_pick_reason(self._card_with_diff(0), slot_items, None)
        assert '5' in reason

    def test_large_diff_formats_eok_cheon(self):
        """1억 5천 → 1억 5천 형식 검증"""
        reason = _make_pick_reason(self._card_with_diff(15_000), [{}], None)
        assert '1억' in reason
        assert '5천' in reason

    def test_exactly_eok_no_cheon(self):
        """정확히 1억 → '1억' (천 없음)"""
        reason = _make_pick_reason(self._card_with_diff(10_000), [{}], None)
        assert '1억' in reason


# ── _make_prompt_regular ──────────────────────────────────────

def _prompt_card(apt_seq='A001', pt='20평대', price=30_000,
                 time_min=25, build_year=2010,
                 bus=0, subway=1, transit_summary='2호선'):
    return {
        'apt_seq': apt_seq,
        'apt_nm': '테스트아파트',
        'umd_nm': '테스트동',
        'pyeong_type': pt,
        'price_low': price,
        'total_time_min': time_min,
        'build_year': build_year,
        'bus_cnt': bus,
        'subway_cnt': subway,
        'transit_summary': transit_summary,
    }


class TestMakePromptRegular:
    def test_returns_string(self):
        prompt = _make_prompt_regular(_prompt_card(), {})
        assert isinstance(prompt, str)

    def test_contains_apt_name(self):
        prompt = _make_prompt_regular(_prompt_card(), {})
        assert '테스트아파트' in prompt

    def test_contains_price(self):
        prompt = _make_prompt_regular(_prompt_card(price=30_000), {})
        assert '3억' in prompt

    def test_contains_time(self):
        prompt = _make_prompt_regular(_prompt_card(time_min=35), {})
        assert '35' in prompt

    def test_no_build_year_no_age_str(self):
        card = _prompt_card(build_year=None)
        prompt = _make_prompt_regular(card, {})
        assert '년차' not in prompt

    def test_with_build_year_shows_age(self):
        from datetime import date
        card = _prompt_card(build_year=date.today().year - 10)
        prompt = _make_prompt_regular(card, {})
        assert '10년차' in prompt

    def test_direct_subway_shows_직통(self):
        card = _prompt_card(bus=0, subway=1)
        prompt = _make_prompt_regular(card, {})
        assert '직통' in prompt

    def test_bus_and_subway_shows_환승(self):
        card = _prompt_card(bus=1, subway=1)
        prompt = _make_prompt_regular(card, {})
        assert '환승' in prompt

    def test_vs_avg_shown_when_avg_exists(self):
        card = _prompt_card(price=30_000)
        prompt = _make_prompt_regular(card, {'20평대': 25_000})
        assert '%' in prompt

    def test_ends_with_한마디(self):
        prompt = _make_prompt_regular(_prompt_card(), {})
        assert '한 마디:' in prompt


# ── _make_prompt_recommend ────────────────────────────────────

class TestMakePromptRecommend:
    def test_returns_string(self):
        prompt = _make_prompt_recommend(_prompt_card(), {}, '강남역')
        assert isinstance(prompt, str)

    def test_contains_apt_name(self):
        prompt = _make_prompt_recommend(_prompt_card(), {}, '강남역')
        assert '테스트아파트' in prompt

    def test_contains_price(self):
        prompt = _make_prompt_recommend(_prompt_card(price=50_000), {}, '역삼역')
        assert '5억' in prompt

    def test_contains_commute_time(self):
        prompt = _make_prompt_recommend(_prompt_card(time_min=42), {}, '역삼역')
        assert '42' in prompt

    def test_직통_when_one_subway(self):
        prompt = _make_prompt_recommend(_prompt_card(bus=0, subway=1), {}, '역삼역')
        assert '직통' in prompt

    def test_환승_when_bus_and_subway(self):
        prompt = _make_prompt_recommend(_prompt_card(bus=1, subway=1), {}, '역삼역')
        assert '환승' in prompt

    def test_build_year_included(self):
        prompt = _make_prompt_recommend(_prompt_card(build_year=2005), {}, '역삼역')
        assert '2005' in prompt

    def test_no_build_year_no_crash(self):
        card = _prompt_card(build_year=None)
        prompt = _make_prompt_recommend(card, {}, '역삼역')
        assert isinstance(prompt, str)
