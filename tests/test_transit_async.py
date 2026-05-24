"""
app/transit.py 비동기 테스트

- _call_one  : ODsay HTTP 단일 호출 (aioresponses 모킹)
- fetch_cells: 전체 파이프라인 (빈 목록 / 성공 / 실패 / API 인증 오류)

IS_SERVERLESS=True 로 파일시스템 쓰기를 건너뛰고,
portable.USE_PG=False 로 SQLite INSERT를 보장한다.
"""
import json
import re
import asyncio
import pytest
import aiohttp
from aioresponses import aioresponses as mock_aio

import app.transit as transit_mod
import app.portable as portable_mod
from app.transit import _call_one, fetch_cells, ODSAY_URL, KEYS

# aioresponses 0.7.x 는 쿼리스트링이 붙은 URL 을 기본값으로 exact-match 함.
# regex 패턴을 쓰면 쿼리스트링을 무시하고 base URL 만으로 매칭 가능.
_ODSAY_RE = re.compile(re.escape(ODSAY_URL))


# ── ODsay 응답 픽스처 헬퍼 ───────────────────────────────────

def _path(total_time=25, bus=0, subway=1):
    """최소 valid ODsay path dict"""
    return {
        'info': {
            'totalTime': total_time,
            'busTransitCount': bus,
            'subwayTransitCount': subway,
            'totalWalk': 300,
        },
        'subPath': [
            {'trafficType': 3, 'sectionTime': 3, 'distance': 150},
            {
                'trafficType': 1, 'sectionTime': total_time, 'distance': 5000,
                'lane': [{'name': '2호선'}],
                'startName': '강남역', 'endName': '역삼역',
            },
            {'trafficType': 3, 'sectionTime': 3, 'distance': 100},
        ],
    }


def _ok_body(total_time=25, bus=0, subway=1) -> str:
    return json.dumps({'result': {'path': [_path(total_time, bus, subway)]}})


def _no_result_body() -> str:
    return json.dumps({'error': {'message': 'no transit route'}})


def _auth_fail_body() -> str:
    return json.dumps({'error': {'message': 'ApiKeyAuthFailed'}})


# ── _call_one 단위 테스트 ──────────────────────────────────────

class TestCallOne:
    async def test_success_returns_ranked(self):
        sem = asyncio.Semaphore(1)
        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_ok_body(), status=200)
            async with aiohttp.ClientSession() as session:
                cell, ranked, raw = await _call_one(
                    session, KEYS[0], sem, 'R08333C28422', 37.49, 127.02,
                )
        assert cell == 'R08333C28422'
        assert len(ranked) >= 1
        assert raw != ''

    async def test_no_result_returns_empty_ranked_with_raw(self):
        """정상 응답이지만 경로 없음 → legit no-transit, 캐시 O"""
        sem = asyncio.Semaphore(1)
        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_no_result_body(), status=200)
            async with aiohttp.ClientSession() as session:
                cell, ranked, raw = await _call_one(
                    session, KEYS[0], sem, 'R08333C28422', 37.49, 127.02,
                )
        assert ranked == []
        assert raw != ''

    async def test_auth_fail_returns_empty_raw(self):
        """ApiKeyAuthFailed → 캐시 X (raw='')"""
        sem = asyncio.Semaphore(1)
        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_auth_fail_body(), status=200)
            async with aiohttp.ClientSession() as session:
                cell, ranked, raw = await _call_one(
                    session, KEYS[0], sem, 'R08333C28422', 37.49, 127.02,
                )
        assert ranked == []
        assert raw == ''

    async def test_network_exception_returns_empty(self):
        """네트워크 오류 → (cell, [], '')"""
        sem = asyncio.Semaphore(1)
        with mock_aio() as m:
            m.get(_ODSAY_RE, exception=aiohttp.ClientError('timeout'))
            async with aiohttp.ClientSession() as session:
                cell, ranked, raw = await _call_one(
                    session, KEYS[0], sem, 'R08333C28422', 37.49, 127.02,
                )
        assert ranked == []
        assert raw == ''

    async def test_cell_code_preserved_in_result(self):
        sem = asyncio.Semaphore(1)
        target = 'R08400C28500'
        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_ok_body(), status=200)
            async with aiohttp.ClientSession() as session:
                cell, _, _ = await _call_one(
                    session, KEYS[0], sem, target, 37.49, 127.02,
                )
        assert cell == target


# ── fetch_cells 통합 테스트 ────────────────────────────────────

def _wp(wp_id=1):
    return {'wp_id': wp_id, 'lat': 37.4979, 'lng': 127.0276,
            'folder_name': 'test_wp', 'address_norm': '강남역 근처'}


def _insert_wp(conn, wp_id=1):
    conn.execute(
        "INSERT OR REPLACE INTO workplaces "
        "(wp_id, address_key, b_code, lat, lng, cells_cached) "
        "VALUES (?, 'key1', '1168010100', 37.4979, 127.0276, 0)",
        (wp_id,),
    )
    conn.commit()


class TestFetchCells:
    async def test_empty_cells_returns_zero_stats(self, mem_db):
        result = await fetch_cells(mem_db, _wp(), [])
        assert result == {'fetched': 0, 'passed': 0, 'failed': 0, 'elapsed_ms': 0}

    async def test_elapsed_ms_is_int(self, mem_db):
        result = await fetch_cells(mem_db, _wp(), [])
        assert isinstance(result['elapsed_ms'], int)

    async def test_success_cell_inserts_cache_row(self, mem_db, monkeypatch):
        monkeypatch.setattr(transit_mod, 'IS_SERVERLESS', True)
        monkeypatch.setattr(portable_mod, 'USE_PG', False)
        _insert_wp(mem_db)

        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_ok_body(), status=200)
            result = await fetch_cells(mem_db, _wp(), ['R08333C28422'])

        assert result['passed'] == 1
        assert result['failed'] == 0
        row = mem_db.execute(
            "SELECT passed_filter FROM transit_cache "
            "WHERE origin_cell='R08333C28422' AND wp_id=1"
        ).fetchone()
        assert row is not None
        assert row[0] == 1

    async def test_success_cell_inserts_route_row(self, mem_db, monkeypatch):
        monkeypatch.setattr(transit_mod, 'IS_SERVERLESS', True)
        monkeypatch.setattr(portable_mod, 'USE_PG', False)
        _insert_wp(mem_db)

        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_ok_body(), status=200)
            await fetch_cells(mem_db, _wp(), ['R08333C28422'])

        rows = mem_db.execute(
            "SELECT rank FROM transit_routes "
            "WHERE origin_cell='R08333C28422' AND wp_id=1"
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0][0] == 1  # rank=1

    async def test_no_result_cell_inserts_failed_cache(self, mem_db, monkeypatch):
        monkeypatch.setattr(transit_mod, 'IS_SERVERLESS', True)
        monkeypatch.setattr(portable_mod, 'USE_PG', False)
        _insert_wp(mem_db)

        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_no_result_body(), status=200)
            result = await fetch_cells(mem_db, _wp(), ['R08333C28422'])

        assert result['failed'] == 1
        assert result['passed'] == 0
        row = mem_db.execute(
            "SELECT passed_filter FROM transit_cache "
            "WHERE origin_cell='R08333C28422'"
        ).fetchone()
        assert row is not None
        assert row[0] == 0

    async def test_multiple_cells_counted(self, mem_db, monkeypatch):
        monkeypatch.setattr(transit_mod, 'IS_SERVERLESS', True)
        monkeypatch.setattr(portable_mod, 'USE_PG', False)
        _insert_wp(mem_db)

        cells = ['R08333C28422', 'R08333C28423', 'R08333C28424']
        with mock_aio() as m:
            for _ in cells:
                m.get(_ODSAY_RE, body=_ok_body(), status=200)
            result = await fetch_cells(mem_db, _wp(), cells)

        assert result['fetched'] == 3

    async def test_workplaces_cells_cached_updated(self, mem_db, monkeypatch):
        monkeypatch.setattr(transit_mod, 'IS_SERVERLESS', True)
        monkeypatch.setattr(portable_mod, 'USE_PG', False)
        _insert_wp(mem_db)

        with mock_aio() as m:
            m.get(_ODSAY_RE, body=_ok_body(), status=200)
            await fetch_cells(mem_db, _wp(), ['R08333C28422'])

        cached = mem_db.execute(
            "SELECT cells_cached FROM workplaces WHERE wp_id=1"
        ).fetchone()[0]
        assert cached == 1
