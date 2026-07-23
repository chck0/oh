# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-07-23 UTC

## ODsay 키 감시
- 종료 코드: 1
- 출력:
```
Traceback (most recent call last):
  File "scripts/monitor_odsay.py", line 29, in <module>
    from config import cfg
  File "config.py", line 69, in <module>
    class _Config:
  File "config.py", line 73, in _Config
    KAKAO_REST_API_KEY: str = _require('KAKAO_REST_API_KEY')
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "config.py", line 27, in _require
    raise EnvironmentError(f"[config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요")
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
  File "config.py", line 69, in <module>
    class _Config:
  File "config.py", line 73, in _Config
    KAKAO_REST_API_KEY: str = _require('KAKAO_REST_API_KEY')
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "config.py", line 27, in _require
    raise EnvironmentError(f"[config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요")
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
```

## 종합 상태
- 조치 필요 항목: 두 스크립트 모두 환경변수 미설정으로 실행 실패
  - 원인: KAKAO_REST_API_KEY (및 의존 환경변수들) 미설정 — config.py 로딩 단계에서 중단
  - 조치: 실행 환경에 `.env` 파일 또는 환경변수(KAKAO_REST_API_KEY, ODSAY_KEY_*, DATABASE_URL 등) 설정 필요
