# Spec: 코드 헬스 베이스라인 — pylint 복구 + Claude 응답 타입 안전 처리

> **상태**: Implemented
> **작성일**: 2026-05-27
> **구현 브랜치**: fix/pylint-crash-and-ai-safety

---

## 1. Why (왜 만드는가)

- 코드 품질 감시 도구(pylint)가 핵심 파일 5개를 전혀 분석하지 못하는 상태 — 린트 점수 0.00/10, 사실상 맹목 상태
- Claude API 응답에서 `.text`를 무조건 꺼내는 코드가 프로덕션 500 에러로 이어질 수 있는 잠재 버그 포함
- 사용자가 얻는 가치: AI 코멘트 생성이 예상치 못한 블록 타입(ThinkingBlock 등)에서도 안전하게 동작; 팀이 코드 품질을 수치로 추적 가능

---

## 2. User Story

```
As a 개발자,
I want to pylint이 모든 파일을 오류 없이 분석하고, Claude API 응답이 어떤 블록 타입이 와도 서버가 죽지 않기를,
so that 코드 품질을 지속적으로 추적하고 AI 코멘트 기능이 안정적으로 동작한다.
```

---

## 3. Scope

### In-scope
- pylint + astroid 버전 업그레이드 (2.x → 4.x)
- `app/ai.py` Claude 응답 파싱 타입 가드 추가
- `requirements-dev.txt` 신규 생성 (dev 의존성 prod 분리)

### Out-of-scope (Non-goals)
- 발견된 lint 경고 전체 수정 (별도 작업)
- `config.py:97` TextIO union-attr 에러 (ai.py/app/ 범위 밖)
- 테스트 파일 작성 (Spec 10 별도)
- CI 파이프라인 연동

---

## 4. Functional Requirements

- F1. `pylint app/` 실행 시 `F0002 astroid-error` 크래시 없이 모든 파일 분석 완료
- F2. `mypy app/ai.py` 실행 시 `union-attr` 에러 0건
- F3. `app/ai.py`의 Claude 응답 파싱이 `TextBlock`이 아닌 블록(ThinkingBlock, ToolUseBlock 등)을 포함한 응답에서도 AttributeError 없이 빈 문자열을 반환
- F4. pylint/astroid/mypy가 `requirements-dev.txt`에 명시되어 Vercel 프로덕션 빌드에 포함되지 않음

---

## 5. Non-functional Requirements

- **안정성**: Claude 응답 블록 타입 추가/변경 시 서버 다운 없음
- **유지보수**: dev 의존성이 prod 배포(Vercel)와 분리되어 빌드 크기 영향 없음
- **호환성**: Python 3.12 `type` 구문을 포함한 의존성 모듈 분석 가능

---

## 6. Data Model

해당 없음 (DB 변경 없음)

---

## 7. API / Interface

```python
# app/ai.py — _call_llm() 내 변경된 파싱 패턴

# Before (위험 — TextBlock 아닌 블록에서 AttributeError)
return msg.content[0].text.strip()

# After (안전 — TextBlock만 필터링, 없으면 빈 문자열)
text = next((b.text for b in msg.content if isinstance(b, anthropic.types.TextBlock)), "")
return text.strip()
```

---

## 8. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| Claude가 ThinkingBlock만 반환 | 빈 문자열 반환, 500 에러 없음 |
| Claude가 ToolUseBlock 포함 응답 | TextBlock만 추출, 나머지 무시 |
| Claude 응답 content 배열이 비어있음 | 빈 문자열 반환 |
| fallback_model 호출 시에도 동일 상황 | 동일하게 안전 처리 |
| pylint이 한국어 변수명 포함 파일 분석 | astroid 4.x에서 정상 처리 |

---

## 9. Acceptance Criteria

- [x] AC1: `pylint app/models.py app/transit.py app/ai.py app/search.py app/main.py` 실행 시 F0002 크래시 0건
- [x] AC2: pylint 종합 점수 8.0/10 이상 (실측 8.73/10)
- [x] AC3: `mypy app/ai.py` 실행 시 union-attr 에러 0건 (기존 22건 → 0건)
- [x] AC4: `app/ai.py`가 TextBlock 외 블록을 포함한 응답에서 빈 문자열을 반환하고 예외를 던지지 않음
- [x] AC5: `requirements-dev.txt`에 pylint>=4.0, astroid>=4.0, mypy>=1.0 명시
- [ ] AC6 (미완): `git push` 권한 이슈로 PR 미머지 — 수동 머지 필요

---

## 10. Open Questions

- Q1: `config.py:97` TextIO union-attr 에러도 수정할 것인가?
- Q2: pylint 경고(8.73/10 → 10/10) 전체 해소를 별도 태스크로 진행할 것인가?
- Q3: GitHub Actions에서 `pylint + mypy`를 CI 체크로 추가할 것인가?

---

## 11. 구현 메모

- **변경된 파일**:
  - `app/ai.py`: `_call_llm()` 내 331, 342번째 줄 파싱 로직 교체
  - `requirements-dev.txt`: 신규 생성
- **근본 원인**: astroid 2.14가 Python 3.12의 `type X = ...` 구문(PEP 695)을 지원하지 않아 `visit_typealias` AttributeError 발생 → astroid/pylint 4.x에서 해결
- **알려진 제약**: `xihuan27-beep` 계정의 push 권한 이슈로 브랜치 `fix/pylint-crash-and-ai-safety`가 remote에 없음. 로컬 커밋 상태로 보존 중
