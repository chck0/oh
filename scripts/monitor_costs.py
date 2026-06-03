"""
Claude API 비용 일일 모니터링 루프 (Level 1 — Schedule + Secure)

실행:  python scripts/monitor_costs.py
결과:  wiki/cost_report.md 에 누적 저장

보안 제약:
  - DB 쓰기 없음 (SELECT만, 읽기 전용)
  - 외부 API 호출 없음 (DB 조회만)
  - 실제 API 키 노출 없음
  - 임계값 초과 시 경고만 출력 (자동 차단 없음 — 인간 게이트)

루프 종료 조건:
  - 당일 + 누적 집계 완료 시 자동 종료
  - DB 연결 실패 시 에러 메시지 출력 후 종료

비용 단가 (2024년 기준, per 1M tokens):
  Haiku  : input $0.80  / output $4.00
  Sonnet : input $3.00  / output $15.00
  Opus   : input $15.00 / output $75.00

토큰 추정 (호출당 평균):
  - recommend 코멘트(Sonnet): 입력 500 + 출력 120 토큰
  - regular 코멘트(Haiku)   : 입력 300 + 출력 60 토큰
  - 채팅(Opus)               : 입력 2000 + 출력 400 토큰
"""

import sys
import os
from datetime import datetime, timezone, date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.db import db_session

REPORT_PATH = os.path.join(ROOT, 'wiki', 'cost_report.md')

# ── 일일 비용 경고 임계값 ─────────────────────────────────────
DAILY_ALERT_USD = 10.0

# ── 모델별 단가 ($/1M tokens) ────────────────────────────────
PRICING = {
    'claude-haiku-4-5':              {'input': 0.80,  'output': 4.00},
    'claude-haiku-4-5-20251001':     {'input': 0.80,  'output': 4.00},
    'claude-sonnet-4-6':             {'input': 3.00,  'output': 15.00},
    'claude-opus-4-8':               {'input': 15.00, 'output': 75.00},
    'claude-opus-4-6':               {'input': 15.00, 'output': 75.00},
}
DEFAULT_PRICE = {'input': 3.00, 'output': 15.00}  # 모를 때 Sonnet 기준

# ── 모델별 평균 토큰 추정 (호출 1회당) ──────────────────────────
AVG_TOKENS = {
    'haiku':  {'input': 300,  'output': 60},
    'sonnet': {'input': 500,  'output': 120},
    'opus':   {'input': 2000, 'output': 400},
}

def _model_family(model: str) -> str:
    m = model.lower()
    if 'haiku'  in m: return 'haiku'
    if 'sonnet' in m: return 'sonnet'
    if 'opus'   in m: return 'opus'
    return 'sonnet'

def _cost_usd(model: str, calls: int) -> float:
    price  = PRICING.get(model, DEFAULT_PRICE)
    family = _model_family(model)
    tokens = AVG_TOKENS.get(family, AVG_TOKENS['sonnet'])
    input_cost  = price['input']  * tokens['input']  * calls / 1_000_000
    output_cost = price['output'] * tokens['output'] * calls / 1_000_000
    return input_cost + output_cost


def fetch_stats(conn) -> tuple[list[dict], list[dict]]:
    """당일·전체 모델별 호출 수 조회. SQLite/Postgres 모두 동작."""
    today      = date.today().isoformat()
    tomorrow   = (date.today() + timedelta(days=1)).isoformat()
    thirty_ago = (date.today() - timedelta(days=30)).isoformat()

    # 당일
    daily_rows = conn.execute("""
        SELECT model, COUNT(*) as cnt
        FROM apt_pt_friend_comment
        WHERE created_at >= ? AND created_at < ?
        GROUP BY model
        ORDER BY cnt DESC
    """, (today, tomorrow)).fetchall()

    # 최근 30일
    total_rows = conn.execute("""
        SELECT model, COUNT(*) as cnt,
               MIN(created_at) as first_date,
               MAX(created_at) as last_date
        FROM apt_pt_friend_comment
        WHERE created_at >= ?
        GROUP BY model
        ORDER BY cnt DESC
    """, (thirty_ago,)).fetchall()

    return (
        [{'model': r['model'], 'calls': r['cnt']} for r in daily_rows],
        [{'model': r['model'], 'calls': r['cnt'],
          'first': r['first_date'], 'last': r['last_date']} for r in total_rows],
    )


def write_report(daily: list[dict], monthly: list[dict], ran_at: str) -> None:
    daily_total_usd  = sum(_cost_usd(r['model'], r['calls']) for r in daily)
    monthly_total_usd = sum(_cost_usd(r['model'], r['calls']) for r in monthly)
    alert = daily_total_usd >= DAILY_ALERT_USD

    lines = [
        '# Claude API 비용 모니터링 리포트',
        '',
        f'> 실행 시각: {ran_at}',
        f'> 일일 임계값: ${DAILY_ALERT_USD:.2f}',
        '',
    ]

    if alert:
        lines += [f'## 🚨 경고: 당일 예상 비용 ${daily_total_usd:.4f} — 임계값 초과!', '']
    else:
        lines += [f'## ✅ 당일 예상 비용: ${daily_total_usd:.4f} (임계값 이하)', '']

    # 당일
    lines += ['## 당일 호출 현황', '']
    if daily:
        lines += ['| 모델 | 호출 수 | 예상 비용(USD) |', '|------|--------|--------------|']
        for r in daily:
            cost = _cost_usd(r['model'], r['calls'])
            lines.append(f"| `{r['model']}` | {r['calls']} | ${cost:.4f} |")
        lines += [f'| **합계** | **{sum(r["calls"] for r in daily)}** '
                  f'| **${daily_total_usd:.4f}** |']
    else:
        lines += ['_당일 호출 없음_']

    # 최근 30일
    lines += ['', '## 최근 30일 누적', '']
    if monthly:
        lines += ['| 모델 | 호출 수 | 첫 날 | 마지막 날 | 예상 비용(USD) |',
                  '|------|--------|-------|----------|--------------|']
        for r in monthly:
            cost = _cost_usd(r['model'], r['calls'])
            lines.append(f"| `{r['model']}` | {r['calls']} | {r['first']} "
                         f"| {r['last']} | ${cost:.4f} |")
        lines += [f'| **합계** | **{sum(r["calls"] for r in monthly)}** | — | — '
                  f'| **${monthly_total_usd:.4f}** |']
    else:
        lines += ['_30일 내 호출 없음_']

    lines += [
        '',
        '## 비용 절감 가이드',
        '',
        '- 당일 $10 초과 → 채팅 rate limit 도입 검토 (사용자당 일 N회)',
        '- Opus 호출 비중 높음 → 짧은 질문은 Haiku 라우팅 검토',
        '- 30일 $100 초과 → Supabase에서 호출 패턴 분석 후 캐시 TTL 축소',
    ]

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'[Cost Monitor] 리포트 저장: {REPORT_PATH}')


def main() -> int:
    ran_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f'[Cost Monitor] 비용 집계 시작 ({ran_at})')

    try:
        with db_session() as conn:
            daily, monthly = fetch_stats(conn)
    except Exception as e:
        print(f'[Cost Monitor] DB 오류: {e}')
        print('  -> DATABASE_URL 환경변수 또는 DB_PATH / apt_pt_friend_comment 테이블을 확인하세요.')
        return 1

    write_report(daily, monthly, ran_at)

    daily_usd = sum(_cost_usd(r['model'], r['calls']) for r in daily)
    print(f'[Cost Monitor] 당일 예상 비용: ${daily_usd:.4f}', end='')
    if daily_usd >= DAILY_ALERT_USD:
        print(f'  [경고] 임계값(${DAILY_ALERT_USD}) 초과!')
    else:
        print('  OK')

    # ── 루프 종료 조건: 집계·리포트 생성 완료 ─────────────────
    print('[Cost Monitor] 완료')
    return 0


if __name__ == '__main__':
    sys.exit(main())
