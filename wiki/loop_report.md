# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-08-26 UTC

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
  OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
  ```

## 종합 상태
- 조치 필요 항목:
  - 두 스크립트 모두 환경변수 미설정으로 실행 실패
  - 누락 환경변수: `KAKAO_REST_API_KEY` (및 ODSAY_KEY_*, DATABASE_URL)
  - 원격 실행 환경(Claude Code on the web)에 `.env` 파일 또는 시크릿이 설정되지 않음
  - 해결: 리포지토리 환경변수(Secrets)를 원격 실행 환경에 등록 필요
