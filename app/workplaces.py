"""
직장 주소 → wp_id 발급 + 폴더 관리
(sandbox/lib_workplace.py에서 정식 이전)

서버리스(Vercel) 환경에서는 파일시스템이 read-only이므로 폴더/메타 파일
생성은 자동 스킵 (cfg.IS_SERVERLESS).
DB 어댑터는 app/db.py 에서 Supabase/SQLite 자동 분기.
"""
import os
import pathlib
import re
import time
import json
import urllib.parse
import urllib.request
from config import cfg
from app.portable import insert_returning_id, get_last_id, list_columns

KAKAO_URL = 'https://dapi.kakao.com/v2/local/search/address.json'
_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitize_for_folder(s: str) -> str:
    s = _UNSAFE_RE.sub('', s)
    s = re.sub(r'\s+', '_', s.strip())
    return s


def resolve(addr_input: str) -> dict | None:
    """카카오 주소검색 → 표준 dict 반환. 실패 시 None."""
    params = urllib.parse.urlencode({'query': addr_input})
    req = urllib.request.Request(
        f'{KAKAO_URL}?{params}',
        headers={'Authorization': f'KakaoAK {cfg.KAKAO_REST_API_KEY}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        import logging
        logging.getLogger('app').warning('Kakao geocode 실패 [%s]: %s', addr_input, e)
        return None

    docs = data.get('documents', [])
    if not docs:
        return None
    d = docs[0]
    a = d.get('address') or {}
    b_code = a.get('b_code') or ''
    main_bun = a.get('main_address_no') or ''
    sub_bun  = a.get('sub_address_no') or ''
    if len(b_code) != 10 or not main_bun:
        return None
    ra = d.get('road_address') or {}
    lat = float(ra.get('y') or d.get('y') or 0) if (ra.get('y') or d.get('y')) else None
    lng = float(ra.get('x') or d.get('x') or 0) if (ra.get('x') or d.get('x')) else None
    return {
        'address_key':  f'{b_code}|{main_bun}|{sub_bun}',
        'address_norm': ra.get('address_name') or a.get('address_name') or addr_input,
        'b_code': b_code, 'main_bun': main_bun, 'sub_bun': sub_bun,
        'lat': lat, 'lng': lng,
    }


_wp_mem_cache: dict[str, dict] = {}  # address_input → wp dict (프로세스 생존 동안 유지)


def get_or_create(conn, addr_input: str) -> dict | None:
    """workplaces UPSERT + 폴더 생성. dict 반환."""
    # 데모 모드(spec-30): 시드된 직장은 Kakao 호출 없이 DB에서 직접 반환.
    # 미일치 시 평소처럼 캐시/DB/Kakao 경로로 진행 → 키가 더미면 정직하게 실패(400).
    if os.getenv('BADUGI_DEMO'):
        row = conn.execute(
            'SELECT * FROM workplaces WHERE address_input=? OR address_norm=? '
            'ORDER BY last_used DESC LIMIT 1', (addr_input, addr_input)
        ).fetchone()
        if row is not None:
            cols = list_columns(conn, 'workplaces')
            return dict(zip(cols, [row[c] for c in cols]))

    # ── 1순위: 인메모리 캐시 → DB/Kakao 완전 생략 ───────────────
    if addr_input in _wp_mem_cache:
        return _wp_mem_cache[addr_input]

    # ── 2순위: DB 조회 → Kakao API 호출 생략 ────────────────────
    cols = list_columns(conn, 'workplaces')
    cached = conn.execute(
        'SELECT * FROM workplaces WHERE address_input = ?', (addr_input,)
    ).fetchone()
    if cached:
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            'UPDATE workplaces SET last_used=?, search_count=search_count+1 WHERE wp_id=?',
            (now, cached['wp_id'])
        )
        conn.commit()
        result = dict(zip(cols, [cached[c] for c in cols]))
        _wp_mem_cache[addr_input] = result
        return result

    # ── 3순위: Kakao REST API geocoding (첫 등록 시만) ──────────
    resolved = resolve(addr_input)
    if not resolved:
        return None
    now = time.strftime('%Y-%m-%d %H:%M:%S')

    row = conn.execute(
        'SELECT * FROM workplaces WHERE address_key = ?',
        (resolved['address_key'],)
    ).fetchone()

    if row is None:
        ins_cols = [
            'address_key', 'address_input', 'address_norm',
            'b_code', 'main_bun', 'sub_bun',
            'lat', 'lng', 'folder_name',
            'first_seen', 'last_used', 'search_count', 'cells_cached',
        ]
        ins_vals = [
            resolved['address_key'], addr_input, resolved['address_norm'],
            resolved['b_code'], resolved['main_bun'], resolved['sub_bun'],
            resolved['lat'], resolved['lng'], '',
            now, now, 1, 0,
        ]
        cur = conn.execute(
            insert_returning_id('workplaces', ins_cols, 'wp_id'),
            ins_vals,
        )
        wp_id = get_last_id(conn, cur, 'workplaces', 'wp_id')
        folder = f'wp_{wp_id:04d}__{_sanitize_for_folder(resolved["address_norm"])}'
        conn.execute('UPDATE workplaces SET folder_name=? WHERE wp_id=?', (folder, wp_id))
        conn.commit()
        # 로컬에서만 raw 아카이브 폴더 생성 (Vercel은 read-only FS)
        if not cfg.IS_SERVERLESS:
            d = raw_dir_by(folder)
            d.mkdir(parents=True, exist_ok=True)
            (d / 'cells').mkdir(exist_ok=True)
            _write_meta(d, wp_id, addr_input, resolved, now)
    else:
        conn.execute(
            'UPDATE workplaces SET last_used=?, search_count=search_count+1 WHERE wp_id=?',
            (now, row['wp_id'])
        )
        conn.commit()

    cols = list_columns(conn, 'workplaces')
    row = conn.execute('SELECT * FROM workplaces WHERE address_key=?',
                       (resolved['address_key'],)).fetchone()
    # row는 _RowProxy(pg) 또는 sqlite3.Row — 둘 다 dict(zip)로 직렬화 가능
    return dict(zip(cols, [row[c] for c in cols]))


def raw_dir_by(folder_name: str) -> pathlib.Path:
    return pathlib.Path(cfg.PROJECT_ROOT) / 'data' / 'raw' / 'odsay' / 'workplaces' / folder_name


def raw_dir(wp_row: dict) -> pathlib.Path:
    return raw_dir_by(wp_row['folder_name'])


def cell_file(wp_row: dict, origin_cell: str) -> pathlib.Path:
    return raw_dir(wp_row) / 'cells' / f'{origin_cell}.json'


def _write_meta(d: pathlib.Path, wp_id, addr_input, resolved, now):
    meta = {
        'wp_id': wp_id, 'address_input': addr_input,
        'address_norm': resolved['address_norm'],
        'address_key': resolved['address_key'],
        'b_code': resolved['b_code'],
        'main_bun': resolved['main_bun'], 'sub_bun': resolved['sub_bun'],
        'lat': resolved['lat'], 'lng': resolved['lng'],
        'registered_at': now,
    }
    (d / 'meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8'
    )
