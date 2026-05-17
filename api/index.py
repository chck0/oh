"""
Vercel Python 서버리스 함수 진입점.

/api/* 와 /health 요청을 이 함수가 받음 (vercel.json rewrites 참조).
정적 파일(web/*)은 Vercel CDN이 직접 서빙 (outputDirectory: "web").

@vercel/python 런타임은 모듈 최상위의 `app` (ASGI/WSGI 호환) 또는 `handler`
를 자동 감지. FastAPI 인스턴스는 ASGI라 그대로 위임.
"""
import sys
from pathlib import Path

# api/index.py 에서 부모 디렉토리(app/, config.py)를 import 가능하게
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402  (FastAPI ASGI 앱)
