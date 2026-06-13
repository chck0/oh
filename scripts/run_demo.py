"""
run_demo.py — 로컬 데모 모드 원커맨드 런처, 크로스 플랫폼 (spec-32)

Windows(PowerShell/cmd)·macOS·Linux 공통:

    python scripts/run_demo.py

1) .env가 없으면 더미 키로 생성 (실제 키가 있으면 그대로 사용)
2) 데모 시드 DB 생성 (멱등)
3) BADUGI_DEMO=1로 uvicorn 기동 → http://localhost:8000/
   (포트 변경: PORT 환경변수)
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ENV_TEMPLATE = """\
# 데모 모드용 더미 키 — 실제 키로 교체하면 친구 채팅/신규 주소 검색도 동작
KAKAO_REST_API_KEY=demo
ODSAY_KEY_1=demo
ODSAY_REFERER_1=http://localhost:8000
DB_PATH=data/apartment.db
"""


def main():
    env_file = ROOT / '.env'
    if not env_file.exists():
        env_file.write_text(_ENV_TEMPLATE, encoding='utf-8')
        print('[run_demo] .env 생성 (더미 키)')

    subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'seed_demo_data.py')],
        cwd=ROOT, check=True,
    )

    port = os.environ.get('PORT', '8000')
    print(f'[run_demo] http://localhost:{port}/ — 검색 주소: 강남역')
    env = dict(os.environ, BADUGI_DEMO='1')
    subprocess.run(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--port', port],
        cwd=ROOT, env=env, check=True,
    )


if __name__ == '__main__':
    main()
