"""
bus_pair_geom의 pending 쌍을 로컬 OSRM으로 도로 라우팅 (Spec 32)

각 정류장 쌍을 OSRM(cfg.OSRM_URL)에 라우팅 → 검증(_route_ok) → linestring/status 갱신.
실패·우회는 직선 fallback(status='straight'). resumable(pending만 처리), 주기 커밋.

사용법: (OSRM 서버 기동 후) python scripts/route_bus_pairs.py
"""
from __future__ import annotations
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from config import cfg

_MAX_DETOUR = 2.6        # 도로경로/직선 상한 (초과 시 직선 fallback)
_MAX_JUMP_DEG = 0.004    # 내부 점프 상한(약 0.35km) — 비정상 스냅 차단


def _parse(c: str) -> tuple[float, float]:
    lng, lat = c.split(',')
    return float(lng), float(lat)


def _route_ok(coords: list[tuple[float, float]],
              a: tuple[float, float], b: tuple[float, float]) -> bool:
    if len(coords) < 2:
        return False
    straight = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    plen = 0.0
    for p, q in zip(coords, coords[1:]):
        g = ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5
        if g > _MAX_JUMP_DEG:
            return False
        plen += g
    if straight > 0 and plen > _MAX_DETOUR * straight + 0.001:
        return False
    return True


def _route(a_str: str, b_str: str):
    """OSRM 라우팅 → (linestring, status). 실패/우회는 직선 fallback."""
    a, b = _parse(a_str), _parse(b_str)
    url = (f'{cfg.OSRM_URL}/route/v1/driving/{a_str};{b_str}'
           '?overview=full&geometries=geojson')
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get('code') == 'Ok':
            geom = data['routes'][0]['geometry']['coordinates']  # [lng,lat]
            coords = [(p[0], p[1]) for p in geom]
            if _route_ok(coords, a, b):
                return ' '.join(f'{x},{y}' for x, y in coords), 'ok'
    except Exception:
        pass
    # 직선 fallback
    return f'{a_str} {b_str}', 'straight'


def main() -> None:
    conn = connect()
    pend = conn.execute(
        "SELECT a, b FROM bus_pair_geom WHERE status='pending'"
    ).fetchall()
    print(f'라우팅 대상(pending): {len(pend)}')
    t0 = time.time()
    ok = straight = 0
    for i, (a, b) in enumerate(pend, 1):
        ls, st = _route(a, b)
        conn.execute(
            'UPDATE bus_pair_geom SET linestring=?, status=? WHERE a=? AND b=?',
            (ls, st, a, b),
        )
        if st == 'ok':
            ok += 1
        else:
            straight += 1
        if i % 500 == 0:
            conn.commit()
            print(f'  {i}/{len(pend)}  ok={ok} straight={straight} '
                  f'({time.time() - t0:.0f}s)')
    conn.commit()
    conn.close()
    print(f'완료: ok={ok} straight={straight} ({time.time() - t0:.0f}s)')


if __name__ == '__main__':
    main()
