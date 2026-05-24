"""
app/transit.py 순수 함수 테스트 (네트워크/DB 미사용)

- cell_of, cell_center  : 그리드 좌표 변환
- haversine             : 두 점 사이 거리(km)
- filter_path           : ODsay 경로 필터링
- rank_paths            : 경로 정렬/랭킹
- to_steps              : subPath → steps 변환
- step_cols             : N번째 step 컬럼 추출
"""
import math
import pytest
from app.transit import (
    GRID,
    ALLOWED_COMBOS,
    WALK_ONLY_MAX_MIN,
    FIRST_LAST_WALK_M,
    TRANSFER_WALK_M,
    cell_of,
    cell_center,
    haversine,
    filter_path,
    rank_paths,
    to_steps,
    step_cols,
)


# ── 헬퍼 ─────────────────────────────────────────────────────

def _path(bt, st, total_time, first_walk_m=200, last_walk_m=100):
    """테스트용 경로 dict 생성. filter_path 검증에 사용."""
    subpath = [
        {'trafficType': 3, 'distance': first_walk_m, 'sectionTime': 5},
    ]
    for _ in range(bt):
        subpath.append({
            'trafficType': 2, 'distance': 5000, 'sectionTime': 15,
            'lane': [{'busNo': '752번'}], 'startName': '출발', 'endName': '도착',
        })
    for _ in range(st):
        subpath.append({
            'trafficType': 1, 'distance': 8000, 'sectionTime': 20,
            'lane': [{'name': '2호선'}], 'startName': 'A역', 'endName': 'B역',
        })
    subpath.append({'trafficType': 3, 'distance': last_walk_m, 'sectionTime': 3})
    return {
        'info': {
            'busTransitCount': bt,
            'subwayTransitCount': st,
            'totalTime': total_time,
            'totalWalk': first_walk_m + last_walk_m,
        },
        'subPath': subpath,
    }


# ── cell_of / cell_center ─────────────────────────────────────

class TestCellOf:
    def test_returns_correct_format(self):
        cell = cell_of(37.5, 127.0)
        assert cell[0] == 'R'
        assert cell[6] == 'C'
        assert len(cell) == 12   # R{5자리}C{5자리}

    def test_index_matches_floor_division(self):
        lat, lng = 37.5, 127.0
        cell = cell_of(lat, lng)
        r_idx = int(cell[1:6])
        c_idx = int(cell[7:12])
        assert r_idx == int(lat / GRID)
        assert c_idx == int(lng / GRID)

    def test_adjacent_cells_differ(self):
        c1 = cell_of(37.5000, 127.0)
        c2 = cell_of(37.5000 + GRID, 127.0)  # 한 칸 위
        c3 = cell_of(37.5000, 127.0 + GRID)  # 한 칸 오른쪽
        assert c1 != c2
        assert c1 != c3

    def test_same_coords_same_cell(self):
        assert cell_of(37.5123, 127.0456) == cell_of(37.5123, 127.0456)

    def test_coords_within_same_grid_give_same_cell(self):
        # 셀 시작점에서 0.1*GRID ~ 0.9*GRID 이동 → 모두 같은 셀
        lat = 37.5000
        idx_lat = int(lat / GRID)
        cell_start = idx_lat * GRID  # 셀의 정확한 시작 경계
        c1 = cell_of(cell_start + GRID * 0.1, 127.0)
        c2 = cell_of(cell_start + GRID * 0.9, 127.0)
        assert c1 == c2


class TestCellCenter:
    def test_center_is_within_grid_of_input(self):
        lat, lng = 37.5, 127.0
        cell = cell_of(lat, lng)
        clat, clng = cell_center(cell)
        assert abs(clat - lat) <= GRID
        assert abs(clng - lng) <= GRID

    def test_explicit_cell_center(self):
        # R08333C28222 → lat=(8333+0.5)*GRID, lng=(28222+0.5)*GRID
        cell = 'R08333C28222'
        clat, clng = cell_center(cell)
        assert clat == pytest.approx((8333 + 0.5) * GRID, rel=1e-9)
        assert clng == pytest.approx((28222 + 0.5) * GRID, rel=1e-9)

    def test_roundtrip_cell_of_then_center(self):
        lat, lng = 37.555, 126.972
        cell = cell_of(lat, lng)
        clat, clng = cell_center(cell)
        # 중심점에서 다시 cell_of 하면 같은 셀이어야 함
        assert cell_of(clat, clng) == cell


# ── haversine ────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine(37.5, 127.0, 37.5, 127.0) == pytest.approx(0, abs=1e-9)

    def test_symmetry(self):
        d1 = haversine(37.5, 127.0, 37.6, 127.1)
        d2 = haversine(37.6, 127.1, 37.5, 127.0)
        assert d1 == pytest.approx(d2, rel=1e-6)

    def test_positive_for_different_points(self):
        assert haversine(37.5, 127.0, 37.6, 127.1) > 0

    def test_approximately_correct_distance(self):
        # 서울시청(37.5665, 126.9780) → 인천(37.4563, 126.7052) ≈ 28~32 km
        d = haversine(37.5665, 126.9780, 37.4563, 126.7052)
        assert 25 < d < 35

    def test_increases_with_distance(self):
        d_small = haversine(37.5, 127.0, 37.501, 127.0)
        d_large = haversine(37.5, 127.0, 37.510, 127.0)
        assert d_large > d_small


# ── filter_path ───────────────────────────────────────────────

class TestFilterPath:
    def test_walk_only_within_limit(self):
        p = {
            'info': {'busTransitCount': 0, 'subwayTransitCount': 0, 'totalTime': WALK_ONLY_MAX_MIN},
            'subPath': [],
        }
        assert filter_path(p) is True

    def test_walk_only_over_limit(self):
        p = {
            'info': {'busTransitCount': 0, 'subwayTransitCount': 0, 'totalTime': WALK_ONLY_MAX_MIN + 1},
            'subPath': [],
        }
        assert filter_path(p) is False

    def test_valid_subway_path(self):
        assert filter_path(_path(0, 1, 25)) is True

    def test_valid_bus_path(self):
        assert filter_path(_path(1, 0, 30)) is True

    def test_valid_bus_subway_combo(self):
        assert filter_path(_path(1, 1, 40)) is True

    def test_invalid_combo_rejected(self):
        # (3, 0) — ALLOWED_COMBOS에 없음
        p = _path(3, 0, 30)
        assert filter_path(p) is False

    def test_first_walk_too_long(self):
        # first_walk > FIRST_LAST_WALK_M
        p = _path(0, 1, 25, first_walk_m=FIRST_LAST_WALK_M + 1)
        assert filter_path(p) is False

    def test_last_walk_too_long(self):
        # last_walk > FIRST_LAST_WALK_M
        p = _path(0, 1, 25, last_walk_m=FIRST_LAST_WALK_M + 1)
        assert filter_path(p) is False

    def test_transfer_walk_too_long(self):
        # 중간 도보(환승) 거리가 TRANSFER_WALK_M 초과
        p = {
            'info': {'busTransitCount': 1, 'subwayTransitCount': 1, 'totalTime': 45},
            'subPath': [
                {'trafficType': 3, 'distance': 200, 'sectionTime': 3},          # 첫 도보 OK
                {'trafficType': 2, 'distance': 5000, 'sectionTime': 15,
                 'lane': [{'busNo': '752번'}], 'startName': 'A', 'endName': 'B'},
                {'trafficType': 3, 'distance': TRANSFER_WALK_M + 1, 'sectionTime': 8},  # 환승도보 초과
                {'trafficType': 1, 'distance': 8000, 'sectionTime': 20,
                 'lane': [{'name': '2호선'}], 'startName': 'C역', 'endName': 'D역'},
                {'trafficType': 3, 'distance': 100, 'sectionTime': 2},          # 마지막 도보 OK
            ],
        }
        assert filter_path(p) is False

    def test_transfer_walk_at_limit_is_ok(self):
        # TRANSFER_WALK_M 정확히 → 통과 (distance > TRANSFER_WALK_M 조건이므로)
        p = {
            'info': {'busTransitCount': 1, 'subwayTransitCount': 1, 'totalTime': 45},
            'subPath': [
                {'trafficType': 3, 'distance': 200, 'sectionTime': 3},
                {'trafficType': 2, 'distance': 5000, 'sectionTime': 15,
                 'lane': [{'busNo': '752번'}], 'startName': 'A', 'endName': 'B'},
                {'trafficType': 3, 'distance': TRANSFER_WALK_M, 'sectionTime': 7},  # 정확히 한계
                {'trafficType': 1, 'distance': 8000, 'sectionTime': 20,
                 'lane': [{'name': '2호선'}], 'startName': 'C역', 'endName': 'D역'},
                {'trafficType': 3, 'distance': 100, 'sectionTime': 2},
            ],
        }
        assert filter_path(p) is True


# ── rank_paths ────────────────────────────────────────────────

class TestRankPaths:
    def test_empty_input_returns_empty(self):
        assert rank_paths([]) == []

    def test_all_invalid_filtered_out(self):
        # (5, 0) — 허용 콤보 아님
        p = _path(5, 0, 30)
        assert rank_paths([p]) == []

    def test_ranks_start_at_one(self):
        ranked = rank_paths([_path(0, 1, 25)])
        assert ranked[0][0] == 1

    def test_subway_ranks_before_bus(self):
        # 지하철(0,1) cls=1 vs 버스(1,0) cls=4
        subway = _path(0, 1, 30)
        bus = _path(1, 0, 20)   # 더 빠르지만 cls가 낮음
        ranked = rank_paths([bus, subway])
        assert ranked[0][1]['info']['subwayTransitCount'] == 1

    def test_same_class_sorted_by_time(self):
        slow = _path(0, 1, 35)
        fast = _path(0, 1, 20)
        ranked = rank_paths([slow, fast])
        assert ranked[0][1]['info']['totalTime'] == 20

    def test_sequential_ranks(self):
        p1 = _path(0, 1, 20)
        p2 = _path(1, 0, 20)
        ranked = rank_paths([p1, p2])
        ranks = [r for r, _ in ranked]
        assert ranks == [1, 2]

    def test_invalid_paths_excluded_from_count(self):
        valid = _path(0, 1, 20)
        invalid = _path(4, 0, 10)  # 허용 안됨
        ranked = rank_paths([valid, invalid])
        assert len(ranked) == 1
        assert ranked[0][0] == 1


# ── to_steps ─────────────────────────────────────────────────

class TestToSteps:
    def test_walk_with_distance(self):
        sp = [{'trafficType': 3, 'distance': 300, 'sectionTime': 5}]
        steps = to_steps(sp)
        assert len(steps) == 1
        assert steps[0]['type'] == '도보'
        assert steps[0]['dist'] == 300

    def test_zero_distance_walk_is_transfer(self):
        sp = [{'trafficType': 3, 'distance': 0, 'sectionTime': 2}]
        steps = to_steps(sp)
        assert steps[0]['type'] == '환승도보'

    def test_subway_step_extracts_line_and_stations(self):
        sp = [{
            'trafficType': 1, 'distance': 8000, 'sectionTime': 20,
            'lane': [{'name': '2호선'}], 'startName': 'A역', 'endName': 'B역',
        }]
        steps = to_steps(sp)
        assert steps[0]['type'] == '지하철'
        assert steps[0]['line'] == '2호선'
        assert steps[0]['from'] == 'A역'
        assert steps[0]['to'] == 'B역'

    def test_bus_step_extracts_bus_number(self):
        sp = [{
            'trafficType': 2, 'distance': 5000, 'sectionTime': 15,
            'lane': [{'busNo': '752번'}], 'startName': 'X정류장', 'endName': 'Y정류장',
        }]
        steps = to_steps(sp)
        assert steps[0]['type'] == '버스'
        assert steps[0]['line'] == '752번'

    def test_max_5_steps_enforced(self):
        sp = [{'trafficType': 3, 'distance': 100, 'sectionTime': 2}] * 10
        steps = to_steps(sp)
        assert len(steps) == 5

    def test_empty_lane_defaults_to_empty_string(self):
        sp = [{'trafficType': 1, 'distance': 5000, 'sectionTime': 15}]  # lane 키 없음
        steps = to_steps(sp)
        assert steps[0]['line'] == ''

    def test_mixed_subpath_order_preserved(self):
        sp = [
            {'trafficType': 3, 'distance': 200, 'sectionTime': 3},
            {'trafficType': 1, 'distance': 8000, 'sectionTime': 20,
             'lane': [{'name': '5호선'}], 'startName': 'S역', 'endName': 'E역'},
        ]
        steps = to_steps(sp)
        assert steps[0]['type'] == '도보'
        assert steps[1]['type'] == '지하철'


# ── step_cols ─────────────────────────────────────────────────

class TestStepCols:
    def _sample_steps(self):
        return [
            {'type': '도보', 'time': 5, 'dist': 200, 'line': '', 'from': '', 'to': ''},
            {'type': '지하철', 'time': 20, 'dist': 8000, 'line': '2호선', 'from': 'A역', 'to': 'B역'},
        ]

    def test_first_step(self):
        t, tm, dm, ln, fr, to = step_cols(self._sample_steps(), 1)
        assert t == '도보'
        assert tm == 5
        assert dm == 200

    def test_second_step(self):
        t, tm, dm, ln, fr, to = step_cols(self._sample_steps(), 2)
        assert t == '지하철'
        assert ln == '2호선'
        assert fr == 'A역'
        assert to == 'B역'

    def test_out_of_range_returns_empty(self):
        t, tm, dm, ln, fr, to = step_cols(self._sample_steps(), 5)
        assert t == ''
        assert tm is None
        assert dm is None
        assert ln == ''
        assert fr == ''
        assert to == ''

    def test_empty_steps_out_of_range(self):
        t, tm, dm, ln, fr, to = step_cols([], 1)
        assert t == ''
        assert tm is None
