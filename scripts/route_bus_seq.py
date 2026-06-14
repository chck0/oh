"""
버스 step '전체 정류장 시퀀스'를 한 번에 OSRM 라우팅 (Spec 32 개선)

쌍 단위 라우팅이 정류장마다 U턴·이음새 꺾임·블록 루프를 만들어서 →
PoC처럼 step 전체 정류장을 한 번에 라우팅(continue_straight)해 매끈하게.
원본 정류장은 raw ODsay JSON에서 읽음(transit_routes는 이미 도로좌표).

bus_seq_geom 캐시(정류장시퀀스 문자열 → 도로 linestring). 검증: detour 비율.
사용법: (OSRM 기동 후) python scripts/route_bus_seq.py
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.db import connect
from app.transit import to_steps, step_cols, MAX_STEPS
from config import cfg

RAW = Path('data/raw/odsay/workplaces')
_MAX_DETOUR = 1.8
_MAX_JUMP = 0.004


def _route(stops: list[str]):
    coords = ';'.join(stops)
    base = (f'{cfg.OSRM_URL}/route/v1/driving/{coords}'
            '?overview=full&geometries=geojson')
    for cs in ('&continue_straight=true', ''):
        try:
            with urllib.request.urlopen(base + cs, timeout=15) as resp:
                data = json.loads(resp.read())
            if data.get('code') != 'Ok':
                continue
            geom = data['routes'][0]['geometry']['coordinates']
            if len(geom) < 2:
                continue
            sp = [tuple(map(float, s.split(','))) for s in stops]
            straight = sum(((sp[i][0]-sp[i+1][0])**2+(sp[i][1]-sp[i+1][1])**2)**0.5
                           for i in range(len(sp)-1))
            plen = 0.0
            bad = False
            for p, q in zip(geom, geom[1:]):
                g = ((p[0]-q[0])**2+(p[1]-q[1])**2)**0.5
                if g > _MAX_JUMP:
                    bad = True
                    break
                plen += g
            if bad:
                continue
            if straight > 0 and plen > _MAX_DETOUR * straight + 0.001:
                continue
            return ' '.join(f'{x},{y}' for x, y in geom), 'ok'
        except Exception:
            continue
    return ' '.join(stops), 'straight'


def main() -> None:
    conn = connect()
    conn.executescript(
        'CREATE TABLE IF NOT EXISTS bus_seq_geom '
        '(stops TEXT PRIMARY KEY, linestring TEXT, status TEXT);')
    conn.commit()

    # raw에서 고유 버스 정류장 시퀀스 수집
    seqs: set[str] = set()
    for wp in RAW.glob('wp_*'):
        if not (wp / 'cells').exists():
            continue
        for cf in (wp / 'cells').glob('*.json'):
            try:
                data = json.loads(cf.read_text(encoding='utf-8'))
            except Exception:
                continue
            for path in data.get('result', {}).get('path', []):
                steps = to_steps(path.get('subPath', []))
                for i in range(1, MAX_STEPS + 1):
                    c = step_cols(steps, i)
                    if c[0] == '버스' and c[6] and len(c[6].split()) >= 2:
                        seqs.add(c[6])
    done = {r[0] for r in conn.execute(
        "SELECT stops FROM bus_seq_geom WHERE status IS NOT NULL")}
    todo = [s for s in seqs if s not in done]
    print(f'고유 버스 시퀀스: {len(seqs)}, 라우팅 대상: {len(todo)}')

    t0 = time.time()
    ok = straight = 0
    for i, s in enumerate(todo, 1):
        ls, st = _route(s.split())
        conn.execute(
            'INSERT OR REPLACE INTO bus_seq_geom (stops, linestring, status) '
            'VALUES (?, ?, ?)', (s, ls, st))
        ok += (st == 'ok')
        straight += (st != 'ok')
        if i % 500 == 0:
            conn.commit()
            print(f'  {i}/{len(todo)} ok={ok} straight={straight} '
                  f'({time.time()-t0:.0f}s)')
    conn.commit()
    conn.close()
    print(f'완료: ok={ok} straight={straight} ({time.time()-t0:.0f}s)')


if __name__ == '__main__':
    main()
