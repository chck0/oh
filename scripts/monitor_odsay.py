"""
ODsay API 키 상태 자동 감시 루프 (Level 1 — Schedule + Secure)

실행:  python scripts/monitor_odsay.py
결과:  wiki/odsay_report.md 에 저장

보안 제약:
  - DB 쓰기 없음 (읽기 전용)
  - 외부 호출은 ODsay API 1곳만 (allowlist 역할)
  - 리포트 파일 외 로컬 파일 수정 없음
  - 키 전체 노출 없음 (앞 8자리만 표시)

루프 종료 조건:
  - 등록된 모든 키 체크 완료 시 자동 종료
  - 키가 0개이면 즉시 종료
"""

import sys
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ── 프로젝트 루트를 sys.path에 추가 ──────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import cfg

# ── 상수 ─────────────────────────────────────────────────────
# 동작구청 → 강남역 (app/main.py _test_odsay와 동일 경로)
TEST_PARAMS = {
    'SX': '126.9395', 'SY': '37.5124',
    'EX': '127.0276', 'EY': '37.4979',
    'lang': '0', 'OPT': '0',
}
TIMEOUT_S = 10
REPORT_PATH = os.path.join(ROOT, 'wiki', 'odsay_report.md')


def check_key(idx: int, k: dict) -> dict:
    """키 1개 실제 호출 테스트 → 결과 dict 반환."""
    params = {**TEST_PARAMS, 'apiKey': k['key']}
    url = 'https://api.odsay.com/v1/api/searchPubTransPathT?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Referer': k['referer'] or ''})

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            body = r.read().decode('utf-8')
            http_status = r.status
    except Exception as e:
        return {
            'idx': idx,
            'key_prefix': k['key'][:8] + '...',
            'status': 'ERROR',
            'http_status': -1,
            'detail': str(e),
        }

    try:
        j = json.loads(body)
        if 'result' in j:
            return {'idx': idx, 'key_prefix': k['key'][:8] + '...', 'status': 'OK',
                    'http_status': http_status, 'detail': '정상'}
        err = j.get('error', {})
        code = err.get('code') if isinstance(err, dict) else None
        msg  = err.get('message') if isinstance(err, dict) else str(err)
        return {'idx': idx, 'key_prefix': k['key'][:8] + '...', 'status': 'FAIL',
                'http_status': http_status, 'detail': f'code={code} {msg}'}
    except Exception as e:
        return {'idx': idx, 'key_prefix': k['key'][:8] + '...', 'status': 'PARSE_ERROR',
                'http_status': http_status, 'detail': str(e)}


def write_report(results: list[dict], ran_at: str) -> None:
    ok    = [r for r in results if r['status'] == 'OK']
    fail  = [r for r in results if r['status'] != 'OK']

    lines = [
        '# ODsay API 키 상태 리포트',
        '',
        f'> 실행 시각: {ran_at}',
        f'> 전체 키: {len(results)}개 | ✅ 정상: {len(ok)}개 | ❌ 이상: {len(fail)}개',
        '',
        '## 결과 상세',
        '',
        '| 번호 | 키 앞자리 | 상태 | HTTP | 메시지 |',
        '|------|-----------|------|------|--------|',
    ]
    for r in results:
        icon = '✅' if r['status'] == 'OK' else '❌'
        lines.append(f"| {r['idx']} | `{r['key_prefix']}` | {icon} {r['status']} "
                     f"| {r['http_status']} | {r['detail']} |")

    if fail:
        lines += ['', '## ⚠️ 조치 필요', '']
        for r in fail:
            lines.append(f"- 키 #{r['idx']} (`{r['key_prefix']}`): {r['detail']}")
        lines += ['', '→ config.py / 환경변수에서 해당 키를 제거하거나 교체하세요.']
    else:
        lines += ['', '## ✅ 모든 키 정상', '', '별도 조치 불필요.']

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'[ODsay Monitor] 리포트 저장: {REPORT_PATH}')


def main() -> int:
    keys = cfg.ODSAY_KEYS
    if not keys:
        print('[ODsay Monitor] 등록된 키 없음. 종료.')
        return 1

    ran_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f'[ODsay Monitor] {len(keys)}개 키 점검 시작 ({ran_at})')

    results = []
    for i, k in enumerate(keys, 1):
        print(f'  키 #{i} 테스트 중...', end=' ', flush=True)
        r = check_key(i, k)
        results.append(r)
        print(r['status'])

    # ── 루프 종료 조건: 모든 키 체크 완료 ──────────────────────
    write_report(results, ran_at)

    ok_count   = sum(1 for r in results if r['status'] == 'OK')
    fail_count = len(results) - ok_count
    print(f'[ODsay Monitor] 완료 - 정상 {ok_count}개 / 이상 {fail_count}개')

    return 0 if fail_count == 0 else 2   # exit 2 = 이상 키 있음


if __name__ == '__main__':
    sys.exit(main())
