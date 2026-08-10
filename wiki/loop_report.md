# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-08-10 UTC

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
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/oh/config.py", line 27, in _require
    raise EnvironmentError(f"[config] 필수 환경변수 누락: {key}  →  .env 파일을 확인하세요")
OSError: [config] 필수 환경변수 누락: KAKAO_REST_API_KEY  →  .env 파일을 확인하세요
```

## 종합 상태
- 조치 필요 항목: 두 스크립트 모두 환경변수 누락으로 실행 실패
  - 누락된 환경변수: `KAKAO_REST_API_KEY` (config.py에서 필수로 요구)
  - `.env` 파일이 없거나 필수 환경변수가 설정되지 않은 상태
  - 모니터링 컨테이너/서버에 `KAKAO_REST_API_KEY` 등 필수 환경변수를 주입해야 합니다
