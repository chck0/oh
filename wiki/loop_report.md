# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-08-08 UTC

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
  OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
  ```

## 종합 상태
- 조치 필요 항목: 두 스크립트 모두 실행 실패 — 환경변수 `KAKAO_REST_API_KEY` (및 기타 필수 환경변수)가 이 실행 환경에 설정되어 있지 않습니다. `.env` 파일을 원격 환경에 배포하거나, GitHub Actions Secrets / 배포 환경에 환경변수를 등록해야 합니다.
