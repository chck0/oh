"""
BADUGI 모니터링 루프 — 지속 실행 (Level 2 Persistent Agent)

컨테이너가 살아있는 동안 매일 09:00 KST(00:00 UTC)에 자동 실행.
즉시 한 번 실행 후 이후 스케줄 유지.
"""
import subprocess
import sys
import os
import time
from datetime import datetime, timezone

SCRIPTS = [
    "scripts/monitor_odsay.py",
    "scripts/monitor_costs.py",
]

def run_monitors():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*50}")
    print(f"[Loop] 모니터링 실행: {now}")
    print(f"{'='*50}")

    for script in SCRIPTS:
        print(f"\n[Loop] 실행: {script}")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode not in (0, 2):   # 0=정상, 2=이상키 발견(경고)
            print(f"[Loop] 오류: {result.stderr}")
        print(f"[Loop] 종료 코드: {result.returncode}")

def seconds_until_next_midnight_utc():
    """다음 00:00 UTC까지 남은 초."""
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (next_midnight - now).total_seconds()

def main():
    print("[Loop] BADUGI 모니터링 컨테이너 시작")
    print("[Loop] 스케줄: 매일 00:00 UTC (09:00 KST)")

    # 시작 즉시 1회 실행
    run_monitors()

    # 이후 매일 00:00 UTC 반복
    while True:
        wait = seconds_until_next_midnight_utc()
        print(f"\n[Loop] 다음 실행까지 {wait/3600:.1f}시간 대기...")
        time.sleep(wait)
        run_monitors()

if __name__ == "__main__":
    main()
