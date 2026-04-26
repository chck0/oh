# /refactor-persona — 페르소나 리팩터 + 테스트 자동 갱신

페르소나 명세서 변경 시, 관련 테스트 키워드도 함께 갱신하는 TDD 루프를 실행한다.

## 순서

1. `agents/*.md` 페르소나 명세서와 `tests/test_personas.py`, `tests/test_demo_mock.py` 읽기
2. 어떤 테스트가 페르소나 키워드/문구에 의존하는지 식별
3. 페르소나 명세서 수정
4. 수정된 내용에 맞춰 테스트의 키워드 assertions도 함께 갱신
5. `src/demo_mock.py`의 Gold Standard 응답도 새 페르소나에 맞게 갱신
6. `pytest tests/ -v` 실행
7. 실패 시 원인 진단 → 수정 → 재실행 (사용자 확인 없이 반복)
8. 전체 통과 시 커밋 + PR 생성

## 핵심 규칙

- 페르소나 파일과 테스트를 **동시에** 수정한다 (페르소나만 고치고 테스트를 나중에 고치지 않는다)
- `src/personas.py`의 DIVERSITY_ANGLES도 새 페르소나에 맞게 갱신
- 내부 코드 키 (`"mentor"`, `"practitioner"`, `"redteam"`, `"clerk"`)는 변경하지 않는다
