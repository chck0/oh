# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-07-17 00:00:00 UTC

## ODsay 키 감시
- 종료 코드: 1
- 출력:
```
Traceback (most recent call last):
  File "/home/user/oh/scripts/monitor_odsay.py", line 29, in <module>
    from config import cfg
  File "/home/user/oh/config.py", line 15, in <module>
    from dotenv import load_dotenv
ModuleNotFoundError: No module named 'dotenv'
```

## Claude API 비용 감시
- 종료 코드: 1
- 출력:
```
Traceback (most recent call last):
  File "/home/user/oh/scripts/monitor_costs.py", line 35, in <module>
    from app.db import db_session
  File "/home/user/oh/app/db.py", line 21, in <module>
    from config import cfg
  File "/home/user/oh/config.py", line 15, in <module>
    from dotenv import load_dotenv
ModuleNotFoundError: No module named 'dotenv'
```

## 종합 상태
- 조치 필요 항목: `python-dotenv` 패키지 미설치로 두 스크립트 모두 실행 불가
  - `pip install python-dotenv` (또는 `pip install -r requirements.txt`) 실행 필요
  - ODsay 키 감시 및 Claude API 비용 감시 모두 스킵됨
  - 환경변수(ODSAY_KEY_*, DATABASE_URL) 설정도 별도로 필요
