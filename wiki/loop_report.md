# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-07-09 00:08:07 UTC

## ODsay 키 감시
- 종료 코드: 1
- 출력:
```
Traceback (most recent call last):
  File "/home/user/oh/scripts/monitor_odsay.py", line 29, in <module>
    from config import cfg
  File "/home/user/oh/config.py", line 69, in <module>
    class _Config:
  File "/home/user/oh/config.py", line 73, in _Config
    KAKAO_REST_API_KEY: str = _require('KAKAO_REST_API_KEY')
  File "/home/user/oh/config.py", line 27, in _require
    raise EnvironmentError(f"[config] 필수 환경변수 누락: {key}  →  .env 파일을 확인하세요")
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
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
  File "/home/user/oh/config.py", line 69, in <module>
    class _Config:
  File "/home/user/oh/config.py", line 73, in _Config
    KAKAO_REST_API_KEY: str = _require('KAKAO_REST_API_KEY')
  File "/home/user/oh/config.py", line 27, in _require
    raise EnvironmentError(f"[config] 필수 환경변수 누락: {key}  →  .env 파일을 확인하세요")
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
```

## 종합 상태
- 조치 필요 항목:
  - **KAKAO_REST_API_KEY** 환경변수 미설정으로 두 스크립트 모두 실행 불가 (exit 1)
  - config.py가 KAKAO_REST_API_KEY를 필수값으로 요구하므로, 모니터링 환경(CI/cron)에도 해당 환경변수를 설정해야 합니다
  - ODSAY_KEY_*, DATABASE_URL도 함께 확인 필요
  - 참고: python-dotenv는 금번 실행 중 설치 완료 (pip install python-dotenv)
