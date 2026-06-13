"""
Supabase(Postgres) → SQLite(data/apartment.db) 다운로드

Supabase DB 전체를 로컬 SQLite로 받아옵니다.
조원들이 로컬 개발 환경을 세팅할 때 사용합니다.

전제:
    DATABASE_URL 환경변수가 세팅되어 있어야 합니다 (.env 또는 shell export).
    예: DATABASE_URL=postgresql://postgres:[PWD]@db.[PROJECT-REF].supabase.co:5432/postgres

사용법:
    python scripts/download_db.py                  # 대화형 (비교 후 질문)
    python scripts/download_db.py --force          # 기존 DB 삭제 후 바로 다운로드
    python scripts/download_db.py --compare-only   # 비교만 하고 종료
    python scripts/download_db.py --skip=trade_history,building_register  # 대용량 테이블 제외
    python scripts/download_db.py --only=apartments,trade_recent          # 특정 테이블만
    python scripts/download_db.py --batch=5000     # 배치 크기 (default 5000)
    python scripts/download_db.py --out=path/to/other.db  # 저장 경로 지정

예상 소요 시간: 1~3분 (636k rows, ~181 MB Postgres 기준)
"""
from __future__ import annotations

import sys
import os
import sqlite3
import argparse
import time
import re
from pathlib import Path

# Windows cp949 콘솔 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 프로젝트 루트의 .env 로드
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv 없어도 환경변수 직접 세팅이면 OK

try:
    import psycopg
except ImportError:
    print("psycopg가 설치되지 않았습니다.  pip install 'psycopg[binary]'")
    sys.exit(1)


# ─── 설정 ──────────────────────────────────────────────────────────────────

DEFAULT_OUT = str(Path(__file__).parent.parent / "data" / "apartment.db")

# 선호 순서 힌트 — 이 목록에 없는 새 테이블은 알파벳순으로 뒤에 붙음.
# 새 테이블이 Supabase에 추가돼도 스크립트 수정 없이 자동으로 포함됨.
_PREFERRED_ORDER = [
    "workplaces",
    "apartments",
    "kapt_complexes",
    "trade_recent",
    "trade_history",
    "apt_walking_poi",
    "apt_hsmp_mapping",
    "apt_slope",
    "grid_cells",
    "transit_cache",
    "transit_routes",
    "apt_friend_comment",
    "apt_pt_friend_comment",
    "building_register",
    "building_register_log",
    "trade_tags",
]

BATCH_SIZE = 5000


# ─── 유틸 ──────────────────────────────────────────────────────────────────

def _pg_connect(url: str) -> "psycopg.Connection":
    """
    Supabase Postgres 연결.

    pgBouncer 호환성 자동 처리:
      1) `:6543` (Transaction pooler) 감지 → `:5432` (Session pooler)로 자동 재작성.
         Transaction pooler는 서버사이드 named cursor(DECLARE CURSOR)를 지원하지 않아
         스트리밍 다운로드가 silent hang 됨. 같은 pooler 호스트의 5432 포트(Session mode)
         로 바꾸면 named cursor가 정상 동작함.
      2) autocommit=False: named cursor는 트랜잭션 블록 안에서만 동작 (psycopg 3.3+).
      3) prepare_threshold=None: pgBouncer가 prepared statement를 차단해도 무방.
      4) connect_timeout=30: 네트워크 hang 시 30초 내 에러로 떨어지게 (silent hang 방지).
      5) statement_timeout=600s: 단일 쿼리가 10분 넘어가면 강제 종료.
    """
    # ── pgBouncer Transaction mode(6543) 감지 후 Session mode(5432)로 자동 전환 ──
    rewritten = re.sub(r"(pooler\.supabase\.com):6543\b", r"\1:5432", url)
    if rewritten != url:
        print(
            "⚠️   DATABASE_URL이 pgBouncer Transaction pooler(:6543)를 가리킵니다.\n"
            "    download_db.py는 서버사이드 커서를 사용하므로 Session pooler(:5432)로\n"
            "    자동 전환하여 연결합니다. (.env는 그대로 두어도 OK)"
        )
        url = rewritten

    conn = psycopg.connect(
        url,
        autocommit=False,
        prepare_threshold=None,
        connect_timeout=30,
        options="-c statement_timeout=600000",  # 10분
    )
    return conn


def _pg_tables(pg: "psycopg.Connection") -> list[str]:
    """
    Postgres public 스키마 테이블 목록.
    _PREFERRED_ORDER 순서대로 먼저 나열하고,
    목록에 없는 신규 테이블은 알파벳순으로 뒤에 붙인다.
    → 스키마 변경(테이블 추가)에 자동 대응.
    """
    with pg.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        all_tables = {row[0] for row in cur.fetchall()}

    ordered = [t for t in _PREFERRED_ORDER if t in all_tables]
    extras = sorted(all_tables - set(ordered))
    return ordered + extras


def _pg_indexes(pg: "psycopg.Connection") -> list[tuple[str, str]]:
    """
    Postgres public 스키마의 인덱스 정의를 직접 조회.
    반환: [(index_name, indexdef), ...]
    → supabase_schema.sql 파일에 의존하지 않아 스키마 변경에 자동 대응.
    """
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexdef NOT LIKE '%UNIQUE%'
            ORDER BY tablename, indexname
            """
        )
        return cur.fetchall()


def _pg_row_count(pg: "psycopg.Connection", table: str) -> int:
    with pg.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {_q(table)}")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def _sqlite_row_count(lite: sqlite3.Connection, table: str) -> int:
    try:
        row = lite.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return -1  # 테이블 없음


def _q(name: str) -> str:
    """Postgres 식별자 안전 인용 (큰따옴표)."""
    return '"' + name.replace('"', '""') + '"'


def _pg_columns(pg: "psycopg.Connection", table: str) -> list[str]:
    """테이블 컬럼명 목록 반환."""
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def _pg_create_stmt(pg: "psycopg.Connection", table: str) -> str:
    """
    Postgres 컬럼 정보로 SQLite CREATE TABLE 문 생성.
    Postgres 타입 → SQLite 타입 매핑 (단순화).
    """
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        rows = cur.fetchall()

    def _sqlite_type(pg_type: str) -> str:
        pg_type = pg_type.lower()
        if "int" in pg_type:
            return "INTEGER"
        if any(x in pg_type for x in ("float", "double", "numeric", "decimal", "real")):
            return "REAL"
        if "bool" in pg_type:
            return "INTEGER"
        return "TEXT"

    col_defs = []
    for col_name, data_type, nullable, default in rows:
        sqlite_type = _sqlite_type(data_type)
        not_null = " NOT NULL" if nullable == "NO" else ""
        col_defs.append(f'    "{col_name}" {sqlite_type}{not_null}')

    return f'CREATE TABLE IF NOT EXISTS "{table}" (\n' + ",\n".join(col_defs) + "\n)"


def _fmt_time(secs: float) -> str:
    if secs < 60:
        return f"{secs:.0f}초"
    m, s = divmod(int(secs), 60)
    return f"{m}분 {s}초"


# ─── 비교 ──────────────────────────────────────────────────────────────────

def compare_dbs(pg_url: str, sqlite_path: str) -> dict:
    """
    Supabase vs 로컬 SQLite 핵심 테이블 row count 비교.
    반환: {"match": bool, "details": [(table, pg_cnt, lite_cnt), ...]}
    """
    print("⏳  Supabase 연결 중...")
    pg = _pg_connect(pg_url)
    lite = sqlite3.connect(sqlite_path)

    details = []
    all_match = True

    print(f"\n{'테이블':<30} {'Supabase':>12} {'로컬 SQLite':>12} {'상태':>6}")
    print("-" * 64)

    # Postgres에 실제 존재하는 테이블 전체를 비교 (신규 테이블도 자동 포함)
    all_pg_tables = _pg_tables(pg)
    for table in all_pg_tables:
        pg_cnt = _pg_row_count(pg, table)
        lite_cnt = _sqlite_row_count(lite, table)
        ok = pg_cnt == lite_cnt and lite_cnt >= 0
        if not ok:
            all_match = False
        status = "✅" if ok else ("❌ 없음" if lite_cnt < 0 else "❌ 다름")
        print(f"  {table:<28} {pg_cnt:>12,} {lite_cnt:>12,}   {status}")
        details.append((table, pg_cnt, lite_cnt))

    print()
    pg.close()
    lite.close()
    return {"match": all_match, "details": details}


# ─── 다운로드 ───────────────────────────────────────────────────────────────

def download(
    pg_url: str,
    sqlite_path: str,
    tables: list[str] | None = None,
    skip: list[str] | None = None,
    batch: int = BATCH_SIZE,
) -> None:
    """Postgres → SQLite 전체 다운로드."""
    out_path = Path(sqlite_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Supabase → SQLite 다운로드")
    print(f"  대상: {out_path}")
    print(f"  배치: {batch:,}행")
    print(f"{'=' * 60}\n")

    print("⏳  Supabase 연결 중...")
    pg = _pg_connect(pg_url)

    # 테이블 목록: --only 지정 시 그것만, 없으면 Postgres에서 전체 동적 조회.
    # 신규 테이블이 Supabase에 추가되면 스크립트 수정 없이 자동 포함됨.
    if tables:
        target_tables = [t for t in tables if t in set(_pg_tables(pg))]
    else:
        target_tables = _pg_tables(pg)
    if skip:
        target_tables = [t for t in target_tables if t not in skip]

    print(f"  테이블: {len(target_tables)}개\n")

    # 사전에 전체 row count 파악
    print("📊  테이블별 행 수 확인 중...\n")
    table_counts: dict[str, int] = {}
    total_rows = 0
    for t in target_tables:
        cnt = _pg_row_count(pg, t)
        table_counts[t] = cnt
        total_rows += cnt
        print(f"    {t:<35} {cnt:>10,}행")

    print(f"\n    합계: {total_rows:,}행\n")
    print(f"예상 소요 시간: {_fmt_time(total_rows / 15000)!r} 내외\n")

    # SQLite 연결 (새로 생성)
    lite = sqlite3.connect(sqlite_path)
    lite.execute("PRAGMA journal_mode=WAL")
    lite.execute("PRAGMA synchronous=NORMAL")
    lite.execute("PRAGMA cache_size=-65536")   # 64 MB
    lite.execute("PRAGMA temp_store=MEMORY")

    grand_start = time.time()
    total_written = 0

    for table in target_tables:
        pg_cnt = table_counts[table]
        cols = _pg_columns(pg, table)
        col_list = ", ".join(_q(c) for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        lite_placeholders = ", ".join(["?"] * len(cols))

        # SQLite 테이블 생성
        create_sql = _pg_create_stmt(pg, table)
        lite.execute(f'DROP TABLE IF EXISTS "{table}"')
        lite.execute(create_sql)

        if pg_cnt == 0:
            print(f"  ⏭  {table} — 건너뜀 (0행)")
            continue

        t_start = time.time()
        written = 0

        print(f"  ⬇  {table} ({pg_cnt:,}행) ", end="", flush=True)

        # server-side 커서로 메모리 효율적 스트리밍
        with pg.cursor(name=f"cur_{table}") as cur:
            cur.execute(f"SELECT {col_list} FROM {_q(table)}")

            while True:
                rows = cur.fetchmany(batch)
                if not rows:
                    break

                # psycopg tuple → Python native 변환 (bool → int for SQLite)
                converted = []
                for row in rows:
                    converted.append(
                        tuple(int(v) if isinstance(v, bool) else v for v in row)
                    )

                with lite:
                    lite.executemany(
                        f'INSERT INTO "{table}" ({", ".join(chr(34)+c+chr(34) for c in cols)}) '
                        f"VALUES ({lite_placeholders})",
                        converted,
                    )

                written += len(rows)
                total_written += len(rows)
                pct = written * 100 // pg_cnt if pg_cnt else 100
                elapsed = time.time() - t_start
                speed = written / elapsed if elapsed > 0 else 0
                print(
                    f"\r  ⬇  {table} ({pg_cnt:,}행)  {pct:3d}%  "
                    f"{written:,}/{pg_cnt:,}  {speed:,.0f}행/s  ",
                    end="",
                    flush=True,
                )

        elapsed = time.time() - t_start
        speed = pg_cnt / elapsed if elapsed > 0 else 0
        print(f"\r  ✅  {table:<35} {pg_cnt:>10,}행  {_fmt_time(elapsed)}  ({speed:,.0f}행/s)")

    # ── 인덱스 일괄 생성 ──────────────────────────────────────────────────
    # pg_indexes 시스템 뷰에서 직접 조회 → supabase_schema.sql 파일 불필요.
    # 스키마에 인덱스가 추가/변경되면 자동 반영됨.
    print("\n🔍  인덱스 생성 중 (Postgres pg_indexes 조회)...")
    pg_idx = _pg_indexes(pg)
    ok_cnt = 0
    for idx_name, indexdef in pg_idx:
        # Postgres indexdef 예: "CREATE INDEX idx_apt_seq ON public.apartments USING btree (apt_seq)"
        # SQLite 변환:
        #   1. "ON public.<table>" → "ON <table>"  (스키마 제거)
        #   2. "USING btree/hash/..." → "" (SQLite는 btree만 지원, 명시 불필요)
        #   3. "CREATE INDEX" → "CREATE INDEX IF NOT EXISTS"
        stmt = indexdef
        stmt = re.sub(r"\bON\s+public\.", "ON ", stmt, flags=re.IGNORECASE)
        stmt = re.sub(r"\bUSING\s+\w+\b", "", stmt, flags=re.IGNORECASE)
        stmt = re.sub(
            r"^CREATE\s+INDEX\b",
            "CREATE INDEX IF NOT EXISTS",
            stmt,
            flags=re.IGNORECASE,
        )
        stmt = stmt.strip()
        try:
            lite.execute(stmt)
            ok_cnt += 1
        except sqlite3.OperationalError:
            pass  # 대상 테이블이 skip됐거나 지원 안 되는 문법
    lite.commit()
    print(f"    {ok_cnt}/{len(pg_idx)}개 인덱스 생성 완료")

    lite.execute("PRAGMA optimize")
    lite.close()
    pg.close()

    total_elapsed = time.time() - grand_start
    db_size_mb = out_path.stat().st_size / 1024 / 1024

    print(f"\n{'=' * 60}")
    print(f"  ✅  완료!  {total_written:,}행  |  {db_size_mb:.1f} MB  |  {_fmt_time(total_elapsed)}")
    print(f"  저장 경로: {out_path}")
    print(f"{'=' * 60}\n")


# ─── 대화형 비교+다운로드 흐름 ──────────────────────────────────────────────

def _update_env_sqlite_mode(sqlite_path: str) -> None:
    """다운로드 완료 후 .env의 DATABASE_URL을 현재 컴퓨터의 SQLite 절대경로로 교체."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print("  ⚠️   .env 파일 없음 — DATABASE_URL 자동 설정 건너뜀")
        return

    abs_path = str(Path(sqlite_path).resolve())
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)

    new_lines = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        # 주석 아닌 DATABASE_URL= 줄을 로컬 경로로 교체
        if not stripped.startswith("#") and stripped.startswith("DATABASE_URL="):
            new_lines.append(f"DATABASE_URL={abs_path}\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        new_lines.append(f"DATABASE_URL={abs_path}\n")

    env_path.write_text("".join(new_lines), encoding="utf-8")
    print(f"\n  ✅  .env 자동 업데이트 완료")
    print(f"      DATABASE_URL={abs_path}")
    print(f"      → 이제 앱이 로컬 SQLite 모드로 동작합니다 (Supabase 차단)")


def interactive_flow(args: argparse.Namespace) -> None:
    """CLAUDE.md 온보딩에서 호출하는 대화형 흐름."""
    raw_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or ""
    # DATABASE_URL이 파일 경로(SQLite 모드)면 Supabase URL이 아님 → SUPABASE_DB_URL에서 찾기
    if raw_url and not raw_url.startswith(("postgresql://", "postgres://")):
        raw_url = os.getenv("SUPABASE_DB_URL") or ""
    pg_url = raw_url
    if not pg_url:
        print(
            "❌  Supabase PostgreSQL URL이 없습니다.\n"
            "    DATABASE_URL=postgresql://... 또는\n"
            "    SUPABASE_DB_URL=postgresql://... 을 .env에 추가하세요."
        )
        sys.exit(1)

    sqlite_path = args.out
    skip = [s.strip() for s in args.skip.split(",")] if args.skip else []
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    batch = args.batch

    existing = Path(sqlite_path).exists()

    # ── 비교만 ────────────────────────────────────────────────────────
    if args.compare_only:
        if not existing:
            print(f"❌  비교 대상 파일이 없습니다: {sqlite_path}")
            sys.exit(1)
        result = compare_dbs(pg_url, sqlite_path)
        if result["match"]:
            print("✅  로컬 DB와 Supabase가 일치합니다.")
        else:
            print("❌  일치하지 않습니다. --force 옵션으로 다시 받을 수 있습니다.")
        sys.exit(0)

    # ── --force: 묻지 않고 바로 ───────────────────────────────────────
    if args.force:
        if existing:
            Path(sqlite_path).unlink()
            print(f"🗑  기존 파일 삭제: {sqlite_path}")
        download(pg_url, sqlite_path, tables=only, skip=skip, batch=batch)
        _update_env_sqlite_mode(sqlite_path)
        return

    # ── 기존 파일 없음 → 그냥 다운로드 ──────────────────────────────
    if not existing:
        print(f"📂  {sqlite_path} 가 없습니다. Supabase에서 다운로드합니다.")
        download(pg_url, sqlite_path, tables=only, skip=skip, batch=batch)
        _update_env_sqlite_mode(sqlite_path)
        return

    # ── 기존 파일 있음 → 비교 후 결정 ───────────────────────────────
    print(f"📂  기존 파일 발견: {sqlite_path}")
    result = compare_dbs(pg_url, sqlite_path)

    if result["match"]:
        ans = input(
            "✅  로컬 DB와 Supabase가 일치합니다. 그래도 새로 받을까요? [y/N] "
        ).strip().lower()
        if ans not in ("y", "yes"):
            print("취소했습니다. 기존 파일을 그대로 사용합니다.")
            _update_env_sqlite_mode(sqlite_path)
            return
    else:
        ans = input(
            "⚠️   로컬 DB와 Supabase가 일치하지 않습니다.\n"
            "    기존 파일을 삭제하고 새로 받을까요? [Y/n] "
        ).strip().lower()
        if ans in ("n", "no"):
            print("취소했습니다. 기존 파일을 그대로 유지합니다.")
            _update_env_sqlite_mode(sqlite_path)
            return

    Path(sqlite_path).unlink()
    print(f"🗑  기존 파일 삭제: {sqlite_path}")
    download(pg_url, sqlite_path, tables=only, skip=skip, batch=batch)
    _update_env_sqlite_mode(sqlite_path)


# ─── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Supabase → SQLite 다운로드",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"저장 경로 (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 파일 삭제 후 바로 다운로드 (확인 없음)",
    )
    parser.add_argument(
        "--compare-only",
        action="store_true",
        help="비교만 하고 다운로드 안 함",
    )
    parser.add_argument(
        "--only",
        default="",
        help="특정 테이블만 다운로드 (쉼표 구분, 예: apartments,trade_recent)",
    )
    parser.add_argument(
        "--skip",
        default="",
        help="제외할 테이블 (쉼표 구분, 예: trade_history,building_register)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=BATCH_SIZE,
        help=f"배치 크기 (default: {BATCH_SIZE})",
    )
    args = parser.parse_args()
    interactive_flow(args)


if __name__ == "__main__":
    main()
