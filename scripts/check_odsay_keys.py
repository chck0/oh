"""
ODsay 키 상태 진단 — 1개씩 순차 호출, 결과 테이블 출력.

사용법:
  python scripts/check_odsay_keys.py

출력: key번호, 키 앞8자리, referer, 상태(OK/FAIL), 응답코드/에러
"""
import sys, time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import urllib.request, urllib.parse
from config import cfg

# 서울시청 → 강남구청 (항상 경로 존재하는 좌표)
SX, SY = 126.9784, 37.5665
EX, EY = 127.0276, 37.5172
ODSAY_URL = 'https://api.odsay.com/v1/api/searchPubTransPathT'
DELAY_SEC = 1.5  # 키 간 딜레이


def check_key(idx, key_info):
    params = urllib.parse.urlencode({
        'apiKey': key_info['key'],
        'SX': SX, 'SY': SY, 'EX': EX, 'EY': EY,
        'lang': 0, 'OPT': 0,
    })
    url = f'{ODSAY_URL}?{params}'
    req = urllib.request.Request(url, headers={'Referer': key_info['referer']})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            elapsed = time.time() - t0
            body = r.read().decode('utf-8', errors='replace')
            data = json.loads(body)
            if 'result' in data:
                paths = len(data['result'].get('path', []))
                return 'OK', f'{paths}개 경로 ({elapsed:.1f}s)'
            err = data.get('error', [{}])
            msg = err[0].get('message', '?') if isinstance(err, list) else err.get('message', '?')
            return 'FAIL', msg
    except Exception as e:
        return 'FAIL', str(e)[:60]


def main():
    keys = cfg.ODSAY_KEYS
    print(f'ODsay 키 진단 — {len(keys)}개\n')
    print(f"{'#':<3} {'키(앞8자)':<12} {'referer':<30} {'상태':<6} 메시지")
    print('-' * 80)
    ok = fail = 0
    for i, k in enumerate(keys):
        status, msg = check_key(i + 1, k)
        mark = '✓' if status == 'OK' else '✗'
        print(f"{i+1:<3} {k['key'][:8]:<12} {k['referer'][:28]:<30} {mark}{status:<5} {msg}")
        if status == 'OK':
            ok += 1
        else:
            fail += 1
        if i < len(keys) - 1:
            time.sleep(DELAY_SEC)
    print('-' * 80)
    print(f'결과: OK {ok}개 / FAIL {fail}개 / 총 {len(keys)}개')
    print()
    print('[설정 확인]')
    print(f'  PER_KEY_CONCURRENCY : {__import__("app.transit", fromlist=["PER_KEY_CONCURRENCY"]).PER_KEY_CONCURRENCY}')
    print(f'  ROUND_SLEEP_MS      : {__import__("app.transit", fromlist=["ROUND_SLEEP_MS"]).ROUND_SLEEP_MS}')


if __name__ == '__main__':
    main()
