# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-06-15T00:00 UTC

## ODsay 키 감시
- 종료 코드: 1
- 출력:
```
Traceback (most recent call last):
  File "scripts/monitor_odsay.py", line 29, in <module>
    from config import cfg
  File "config.py", line 69, in _Config
    KAKAO_REST_API_KEY: str = _require('KAKAO_REST_API_KEY')
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
```

## Claude API 비용 감시
- 종료 코드: 1
- 출력:
```
Traceback (most recent call last):
  File "scripts/monitor_costs.py", line 35, in <module>
    from app.db import db_session
  File "app/db.py", line 21, in <module>
    from config import cfg
  File "config.py", line 69, in _Config
    KAKAO_REST_API_KEY: str = _require('KAKAO_REST_API_KEY')
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
```

## 종합 상태
- 조치 필요 항목:
  - `KAKAO_REST_API_KEY` 환경변수가 실행 환경에 설정되어 있지 않아 두 스크립트 모두 시작 단계에서 실패함
  - `ODSAY_KEY_*`, `DATABASE_URL` 환경변수 설정 여부도 확인 필요
  - `.env` 파일 또는 CI/CD 시크릿에 필수 환경변수를 설정 후 재실행 권장
