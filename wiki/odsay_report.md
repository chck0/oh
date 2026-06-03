# ODsay API 키 상태 리포트

> 실행 시각: 2026-06-03 02:09 UTC
> 전체 키: 7개 | ✅ 정상: 5개 | ❌ 이상: 2개

## 결과 상세

| 번호 | 키 앞자리 | 상태 | HTTP | 메시지 |
|------|-----------|------|------|--------|
| 1 | `Jscz0XLP...` | ✅ OK | 200 | 정상 |
| 2 | `JaE9HUiL...` | ✅ OK | 200 | 정상 |
| 3 | `tir5ewrR...` | ❌ FAIL | 200 | code=None [{'code': '500', 'message': '[ApiKeyAuthFailed] ApiKey authentication failed.'}] |
| 4 | `TE0v8qmG...` | ✅ OK | 200 | 정상 |
| 5 | `Lvksqk5v...` | ✅ OK | 200 | 정상 |
| 6 | `dW9cReW9...` | ✅ OK | 200 | 정상 |
| 7 | `1O9bht9L...` | ❌ FAIL | 200 | code=None [{'code': '500', 'message': '[ApiKeyAuthFailed] ApiKey authentication failed.'}] |

## ⚠️ 조치 필요

- 키 #3 (`tir5ewrR...`): code=None [{'code': '500', 'message': '[ApiKeyAuthFailed] ApiKey authentication failed.'}]
- 키 #7 (`1O9bht9L...`): code=None [{'code': '500', 'message': '[ApiKeyAuthFailed] ApiKey authentication failed.'}]

→ config.py / 환경변수에서 해당 키를 제거하거나 교체하세요.
