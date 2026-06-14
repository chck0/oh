"""
app/models.py Pydantic 스키마 검증 테스트

- SearchRequest  : 입력 검증 + 기본값
- TransitStep    : alias("from") 포함 필드 파싱
- AptResult      : 기본 직렬화
"""
import pytest
from pydantic import ValidationError
from app.search import SearchRequest          # 실제 사용되는 SearchRequest (search.py)
from app.models import TransitStep, AptResult  # 공용 응답 스키마


# ── SearchRequest ─────────────────────────────────────────────

class TestSearchRequest:
    def test_required_field_only(self):
        req = SearchRequest(workplace_address='서울시 강남구')
        assert req.workplace_address == '서울시 강남구'

    def test_default_max_minutes(self):
        req = SearchRequest(workplace_address='서울')
        assert req.max_minutes == 60

    def test_default_max_price(self):
        req = SearchRequest(workplace_address='서울')
        assert req.max_price == 50_000

    def test_default_pyeong_types(self):
        req = SearchRequest(workplace_address='서울')
        assert req.pyeong_types == ['10평대', '20평대']  # search.py 기본값

    def test_custom_values(self):
        req = SearchRequest(
            workplace_address='부산광역시 해운대구',
            max_minutes=45,
            max_price=40_000,
            pyeong_types=['30평대', '40평대'],
        )
        assert req.max_minutes == 45
        assert req.max_price == 40_000
        assert req.pyeong_types == ['30평대', '40평대']

    def test_max_minutes_minimum_boundary(self):
        req = SearchRequest(workplace_address='서울', max_minutes=10)
        assert req.max_minutes == 10

    def test_max_minutes_maximum_boundary(self):
        req = SearchRequest(workplace_address='서울', max_minutes=60)  # le=60
        assert req.max_minutes == 60

    def test_max_minutes_below_min_raises(self):
        with pytest.raises(ValidationError):
            SearchRequest(workplace_address='서울', max_minutes=9)

    def test_max_minutes_above_max_raises(self):
        with pytest.raises(ValidationError):
            SearchRequest(workplace_address='서울', max_minutes=61)  # le=60

    def test_missing_workplace_address_raises(self):
        with pytest.raises(ValidationError):
            SearchRequest()  # type: ignore[call-arg]

    def test_multiple_pyeong_types(self):
        req = SearchRequest(
            workplace_address='서울',
            pyeong_types=['20평대', '30평대', '40평대'],
        )
        assert len(req.pyeong_types) == 3


# ── TransitStep ───────────────────────────────────────────────

class TestTransitStep:
    def test_minimal_required_field(self):
        step = TransitStep(type='도보')
        assert step.type == '도보'

    def test_defaults_for_optional_fields(self):
        step = TransitStep(type='지하철')
        assert step.time_min is None
        assert step.dist_m is None
        assert step.line == ''
        assert step.from_ == ''
        assert step.to == ''

    def test_from_alias_populated(self):
        # alias="from" 이므로 dict에서는 'from' 키로 전달
        step = TransitStep(**{'type': '지하철', 'from': 'A역', 'to': 'B역', 'line': '2호선'})
        assert step.from_ == 'A역'

    def test_full_fields(self):
        step = TransitStep(**{
            'type': '버스',
            'time_min': 15,
            'dist_m': 5000,
            'line': '752번',
            'from': '강남역',
            'to': '신논현역',
        })
        assert step.type == '버스'
        assert step.time_min == 15
        assert step.dist_m == 5000
        assert step.line == '752번'
        assert step.from_ == '강남역'
        assert step.to == '신논현역'

    def test_walk_type_no_line(self):
        step = TransitStep(type='도보', time_min=5, dist_m=300)
        assert step.type == '도보'
        assert step.line == ''


# ── AptResult ─────────────────────────────────────────────────

class TestAptResult:
    def test_basic_creation(self):
        apt = AptResult(
            apt_seq='11110-100',
            apt_nm='한강뷰아파트',
            umd_nm='서초동',
            kaptdaCnt=500,
            total_time_min=25,
            steps=[],
        )
        assert apt.apt_seq == '11110-100'
        assert apt.apt_nm == '한강뷰아파트'
        assert apt.steps == []

    def test_with_steps(self):
        step = TransitStep(**{'type': '지하철', 'from': 'A역', 'to': 'B역', 'line': '2호선'})
        apt = AptResult(
            apt_seq='A001',
            apt_nm='테스트아파트',
            umd_nm='마포동',
            kaptdaCnt=300,
            total_time_min=30,
            steps=[step],
        )
        assert len(apt.steps) == 1
        assert apt.steps[0].line == '2호선'

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            AptResult(
                apt_seq='A001',
                # apt_nm 누락
                umd_nm='서초동',
                kaptdaCnt=300,
                total_time_min=25,
                steps=[],
            )  # type: ignore[call-arg]
