# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-09-12T00:08:21 UTC

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
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/oh/config.py", line 27, in _require
    raise EnvironmentError(f"[config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요")
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
```
- 원인: 실행 환경에 필수 환경변수(KAKAO_REST_API_KEY 등)가 설정되지 않음

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
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/oh/config.py", line 27, in _require
    raise EnvironmentError(f"[config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요")
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
```
- 원인: 실행 환경에 필수 환경변수(KAKAO_REST_API_KEY 등)가 설정되지 않음

## 종합 상태
- 조치 필요 항목: 환경변수 미설정으로 두 스크립트 모두 실행 불가
  - `KAKAO_REST_API_KEY` 누락 (config.py의 필수 변수 검증 실패)
  - `ODSAY_KEY_*` 및 `DATABASE_URL` 도 미설정 상태로 추정됨
  - 실제 모니터링 환경(.env 또는 시스템 환경변수)에 해당 변수들을 설정해야 스크립트가 정상 동작합니다
