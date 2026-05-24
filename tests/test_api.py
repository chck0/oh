"""
FastAPI 엔드포인트 스모크 테스트

- GET /health           : 서버 상태 응답 구조 검증
- GET /api/_debug       : DEBUG_API=0 이면 404
- GET /api/_test_kakao  : 진단 엔드포인트 (모듈 임포트 오류 없음 검증)
"""
import os
import pytest


class TestHealthEndpoint:
    def test_returns_200(self, client):
        response = client.get('/health')
        assert response.status_code == 200

    def test_response_is_json(self, client):
        response = client.get('/health')
        data = response.json()
        assert isinstance(data, dict)

    def test_has_status_field(self, client):
        response = client.get('/health')
        assert 'status' in response.json()

    def test_has_backend_field(self, client):
        response = client.get('/health')
        assert 'backend' in response.json()

    def test_status_is_ok_or_import_failed(self, client):
        status = response = client.get('/health').json()['status']
        assert status in ('ok', 'import_failed')

    def test_backend_field_is_valid_value(self, client):
        # .env에 DATABASE_URL 유무에 따라 sqlite 또는 supabase
        data = client.get('/health').json()
        assert data['backend'] in ('sqlite', 'supabase')


class TestDebugEndpoint:
    def test_debug_disabled_returns_404(self, client):
        # DEBUG_API 환경변수가 '1'이 아니면 404
        response = client.get('/api/_debug')
        assert response.status_code == 404

    def test_debug_disabled_returns_json(self, client):
        response = client.get('/api/_debug')
        data = response.json()
        assert 'error' in data

    def test_debug_enabled_returns_200(self, client, monkeypatch):
        # DEBUG_API=1 로 활성화하면 200 반환해야 함
        # app/main.py 가 이미 import 됐으므로 module 변수를 직접 패치
        import app.main as main_module
        monkeypatch.setattr(main_module, 'DEBUG_API', True)
        response = client.get('/api/_debug')
        assert response.status_code == 200

    def test_debug_enabled_has_serverless_field(self, client, monkeypatch):
        import app.main as main_module
        monkeypatch.setattr(main_module, 'DEBUG_API', True)
        data = client.get('/api/_debug').json()
        assert 'serverless' in data


class TestNotFound:
    def test_unknown_path_returns_404(self, client):
        response = client.get('/api/nonexistent_route_xyz')
        assert response.status_code == 404


class TestDebugEnabled:
    """DEBUG_API=True 로 패치했을 때 /api/_debug 완전 응답 검증"""

    def test_has_env_field(self, client, monkeypatch):
        import app.main as m
        monkeypatch.setattr(m, 'DEBUG_API', True)
        data = client.get('/api/_debug').json()
        assert 'env' in data

    def test_has_db_field(self, client, monkeypatch):
        import app.main as m
        monkeypatch.setattr(m, 'DEBUG_API', True)
        data = client.get('/api/_debug').json()
        assert 'db' in data

    def test_db_status_is_ok_or_err(self, client, monkeypatch):
        import app.main as m
        monkeypatch.setattr(m, 'DEBUG_API', True)
        data = client.get('/api/_debug').json()
        assert 'status' in data['db']

    def test_env_contains_key_markers(self, client, monkeypatch):
        import app.main as m
        monkeypatch.setattr(m, 'DEBUG_API', True)
        data = client.get('/api/_debug').json()
        # 주요 환경변수 키가 env 필드에 모두 있어야 함
        for key in ['DATABASE_URL', 'KAKAO_REST_API_KEY', 'ANTHROPIC_API_KEY']:
            assert key in data['env']

    def test_import_error_field_present(self, client, monkeypatch):
        import app.main as m
        monkeypatch.setattr(m, 'DEBUG_API', True)
        data = client.get('/api/_debug').json()
        assert 'import_error' in data


class TestOdsayTestEndpoint:
    """GET /api/_test_odsay — DEBUG_API=True 일 때 응답 검증"""

    def test_disabled_returns_404(self, client):
        resp = client.get('/api/_test_odsay')
        assert resp.status_code == 404

    def test_enabled_returns_results_list(self, client, monkeypatch):
        import app.main as m
        import urllib.request
        monkeypatch.setattr(m, 'DEBUG_API', True)

        # urllib.urlopen 을 모킹해서 외부 호출 차단
        fake_body = b'{"result": {"path": []}}'

        class _FakeResp:
            status = 200
            def read(self):
                return fake_body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **kw: _FakeResp())
        data = client.get('/api/_test_odsay').json()
        assert 'results' in data
        assert isinstance(data['results'], list)


class TestKakaoTestEndpoint:
    """GET /api/_test_kakao — DEBUG_API=True 일 때 응답 검증"""

    def test_disabled_returns_404(self, client):
        resp = client.get('/api/_test_kakao')
        assert resp.status_code == 404

    def test_enabled_returns_http_status(self, client, monkeypatch):
        import app.main as m
        import urllib.request
        monkeypatch.setattr(m, 'DEBUG_API', True)

        fake_body = b'{"documents": []}'

        class _FakeResp:
            status = 200
            def read(self):
                return fake_body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **kw: _FakeResp())
        data = client.get('/api/_test_kakao').json()
        assert 'http_status' in data or 'body_excerpt' in data
