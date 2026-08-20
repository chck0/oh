# BADUGI 자동 모니터링 루프 리포트
> 실행 시각: 2026-08-20 UTC

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
- 조치 필요 항목: 필수 환경변수 누락으로 두 스크립트 모두 실행 실패
  - 누락 환경변수: `KAKAO_REST_API_KEY` (및 기타 .env 필수 변수)
  - 스크립트가 `config.py`의 `_require()` 함수에서 환경변수를 확인하지 못해 오류 발생
  - 조치: 실행 환경에 `.env` 파일 또는 환경변수를 올바르게 설정해야 합니다
