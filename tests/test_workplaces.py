"""
app/workplaces.py 단위 테스트

- _sanitize_for_folder : 파일시스템 안전 문자열 변환 (순수함수)
- resolve              : Kakao 주소 API 호출 (urllib 모킹)
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from app.workplaces import _sanitize_for_folder, resolve


# ── _sanitize_for_folder ──────────────────────────────────────

class TestSanitizeForFolder:
    def test_slash_removed(self):
        assert '/' not in _sanitize_for_folder('a/b')

    def test_colon_removed(self):
        assert ':' not in _sanitize_for_folder('C:path')

    def test_asterisk_removed(self):
        assert '*' not in _sanitize_for_folder('a*b')

    def test_question_mark_removed(self):
        assert '?' not in _sanitize_for_folder('a?b')

    def test_pipe_removed(self):
        assert '|' not in _sanitize_for_folder('a|b')

    def test_space_becomes_underscore(self):
        result = _sanitize_for_folder('서울 강남구')
        assert ' ' not in result
        assert '_' in result

    def test_multiple_spaces_collapse_to_one_underscore(self):
        assert _sanitize_for_folder('a   b') == 'a_b'

    def test_leading_trailing_spaces_stripped(self):
        assert _sanitize_for_folder('  hello  ') == 'hello'

    def test_plain_korean_unchanged(self):
        assert _sanitize_for_folder('강남구') == '강남구'

    def test_empty_unsafe_only_returns_empty(self):
        result = _sanitize_for_folder('///')
        assert result == ''


# ── resolve (Kakao API 모킹) ──────────────────────────────────

def _kakao_doc(b_code='1168010100', main_bun='504', lat='37.4979', lng='127.0276'):
    """정상 Kakao 응답 document 1개"""
    return {
        'address': {
            'b_code': b_code,
            'main_address_no': main_bun,
            'sub_address_no': '',
            'address_name': '서울 강남구 테헤란로 504',
        },
        'road_address': {
            'address_name': '서울특별시 강남구 테헤란로 504',
            'x': lng,
            'y': lat,
        },
        'x': lng,
        'y': lat,
    }


def _mock_urlopen(payload: dict):
    """urllib.request.urlopen 을 payload dict 로 모킹하는 컨텍스트 헬퍼."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode('utf-8')
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch('urllib.request.urlopen', return_value=mock_resp)


class TestResolve:
    def test_success_returns_dict(self):
        payload = {'documents': [_kakao_doc()]}
        with _mock_urlopen(payload):
            result = resolve('서울 강남구 테헤란로 504')
        assert result is not None
        assert result['lat'] == pytest.approx(37.4979)
        assert result['lng'] == pytest.approx(127.0276)

    def test_b_code_in_result(self):
        payload = {'documents': [_kakao_doc()]}
        with _mock_urlopen(payload):
            result = resolve('서울 강남구 테헤란로 504')
        assert result['b_code'] == '1168010100'

    def test_address_key_format_contains_pipe(self):
        payload = {'documents': [_kakao_doc()]}
        with _mock_urlopen(payload):
            result = resolve('서울 강남구 테헤란로 504')
        assert result['address_key'].count('|') == 2

    def test_empty_documents_returns_none(self):
        with _mock_urlopen({'documents': []}):
            result = resolve('존재안하는주소')
        assert result is None

    def test_network_exception_returns_none(self):
        with patch('urllib.request.urlopen', side_effect=OSError('network error')):
            result = resolve('서울 어딘가')
        assert result is None

    def test_b_code_too_short_returns_none(self):
        payload = {'documents': [_kakao_doc(b_code='123')]}
        with _mock_urlopen(payload):
            result = resolve('테스트')
        assert result is None

    def test_missing_main_bun_returns_none(self):
        payload = {'documents': [_kakao_doc(main_bun='')]}
        with _mock_urlopen(payload):
            result = resolve('테스트')
        assert result is None

    def test_address_norm_falls_back_to_input(self):
        """road_address 없을 때 address_name fallback"""
        doc = _kakao_doc()
        doc['road_address'] = None  # road_address 없음
        with _mock_urlopen({'documents': [doc]}):
            result = resolve('테스트주소')
        assert result is not None
        assert result['address_norm']  # 빈 문자열 아님


# ── 데모 모드 게이트 (spec-30) ────────────────────────────────

class TestDemoModeGate:
    """BADUGI_DEMO=1 + 시드된 직장 → Kakao 호출 없이 DB 행 반환."""

    def _seed_wp(self, conn):
        conn.execute(
            "INSERT INTO workplaces (wp_id, address_key, address_input,"
            " address_norm, b_code, lat, lng, folder_name)"
            " VALUES (1, 'DEMO|gangnam|0', '강남역', '서울 강남구 테헤란로 504',"
            " '1168010100', 37.4979, 127.0276, 'wp_0001__demo')")
        conn.commit()

    def test_demo_seeded_address_skips_kakao(self, mem_db, monkeypatch):
        from app import workplaces
        monkeypatch.setenv('BADUGI_DEMO', '1')
        self._seed_wp(mem_db)
        with patch.object(workplaces, 'resolve') as mock_resolve:
            wp = workplaces.get_or_create(mem_db, '강남역')
        mock_resolve.assert_not_called()
        assert wp is not None
        assert wp['wp_id'] == 1

    def test_demo_unseeded_address_falls_through_to_kakao(self, mem_db, monkeypatch):
        from app import workplaces
        monkeypatch.setenv('BADUGI_DEMO', '1')
        self._seed_wp(mem_db)
        with patch.object(workplaces, 'resolve', return_value=None) as mock_resolve:
            wp = workplaces.get_or_create(mem_db, '없는주소')
        mock_resolve.assert_called_once()
        assert wp is None

    def test_no_demo_env_behaves_as_before(self, mem_db, monkeypatch):
        from app import workplaces
        monkeypatch.delenv('BADUGI_DEMO', raising=False)
        self._seed_wp(mem_db)
        with patch.object(workplaces, 'resolve', return_value=None) as mock_resolve:
            wp = workplaces.get_or_create(mem_db, '강남역')
        mock_resolve.assert_called_once()
        assert wp is None
