#!/usr/bin/env bash
# run_demo.sh — 로컬 데모 모드 원커맨드 런처 (spec-32)
#
#   bash scripts/run_demo.sh
#
# 1) .env가 없으면 더미 키로 생성 (실제 키가 있으면 그대로 사용)
# 2) 데모 시드 DB 생성 (멱등)
# 3) BADUGI_DEMO=1로 uvicorn 기동 → http://localhost:8000/
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cat > .env <<'EOF'
# 데모 모드용 더미 키 — 실제 키로 교체하면 친구 채팅/신규 주소 검색도 동작
KAKAO_REST_API_KEY=demo
ODSAY_KEY_1=demo
ODSAY_REFERER_1=http://localhost:8000
DB_PATH=data/apartment.db
EOF
  echo '[run_demo] .env 생성 (더미 키)'
fi

python scripts/seed_demo_data.py

echo '[run_demo] http://localhost:8000/ — 검색 주소: 강남역'
BADUGI_DEMO=1 exec python -m uvicorn app.main:app --port "${PORT:-8000}"
