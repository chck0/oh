# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-08-21T00:00:00Z (UTC)

## ODsay 키 감시
- 종료 코드: 1
- 출력:
  ```
  Traceback (most recent call last):
    File "scripts/monitor_odsay.py", line 29, in <module>
      from config import cfg
    File "config.py", line 69, in _Config
  OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY → .env 파일을 확인하세요
  ```
  → 환경변수(KAKAO_REST_API_KEY 등)가 설정되지 않아 스크립트 실행 불가

## Claude API 비용 감시
- 종료 코드: 1
- 출력:
  ```
  Traceback (most recent call last):
    File "scripts/monitor_costs.py", line 35, in <module>
      from app.db import db_session
    File "config.py", line 69, in _Config
  OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY → .env 파일을 확인하세요
  ```
  → 동일하게 환경변수 미설정으로 실행 불가

## 종합 상태
- 조치 필요 항목: **환경변수 미설정으로 두 스크립트 모두 실행 실패**
  - `KAKAO_REST_API_KEY`, `ODSAY_KEY_*`, `DATABASE_URL` 등 필수 환경변수를
    실행 환경(CI/CD secret 또는 .env 파일)에 등록해야 모니터링이 정상 작동합니다.
