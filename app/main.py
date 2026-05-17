"""
FastAPI 진입점

로컬:    uvicorn app.main:app --reload --port 8000
Vercel:  api/index.py 가 이 app을 import해서 서빙
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.search import router as search_router
from app.db import connect as db_connect, USE_PG

IS_SERVERLESS = bool(os.getenv('VERCEL'))

app = FastAPI(title="real_estate", version="0.1.0")


# ── 앱 시작 시 DB 스키마 보정 ────────────────────────────────
# Postgres(Supabase)에서는 schema가 supabase_schema.sql로 사전 생성됨 →
# 매 cold start마다 DDL 실행하지 않음.
# SQLite(로컬)에서는 신규 테이블 자동 생성 유지.
@app.on_event("startup")
def _ensure_schema():
    if USE_PG:
        return  # Supabase는 schema 사전 적용 — scripts/supabase_schema.sql 참조
    conn = db_connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS apt_friend_comment (
                apt_seq   TEXT NOT NULL,
                wp_id     INTEGER NOT NULL,
                tier      TEXT NOT NULL,
                comment   TEXT NOT NULL,
                model     TEXT DEFAULT 'claude-haiku-4-5',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (apt_seq, wp_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS apt_pt_friend_comment (
                apt_seq      TEXT NOT NULL,
                pyeong_type  TEXT NOT NULL,
                wp_id        INTEGER NOT NULL,
                comment      TEXT NOT NULL,
                model        TEXT DEFAULT 'claude-haiku-4-5',
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (apt_seq, pyeong_type, wp_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 헬스체크 ─────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "backend": "supabase" if USE_PG else "sqlite"}


# ── API 라우터 ───────────────────────────────────────────────
app.include_router(search_router, prefix="/api")


# ── 정적 프론트엔드 (/web/*) ─────────────────────────────────
# Vercel에서는 vercel.json의 rewrites가 /web/* 를 CDN에서 직접 서빙.
# FastAPI 마운트는 로컬 dev 전용.
if not IS_SERVERLESS:
    WEB_DIR = Path(__file__).parent.parent / 'web'
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
