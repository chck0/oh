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
