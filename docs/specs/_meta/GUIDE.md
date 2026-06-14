# Spec 작성 가이드

Spec은 **큰 작업**(여러 파일·새 DB 테이블·새 API·여러 Phase)에만 쓴다.
버그픽스·리팩토링·소규모 수정은 worklog만 남기고 Spec 생략.

## 어떻게

1. `_meta/template.md` 복사 → `docs/specs/NN-feature-name.md` (NN은 다음 번호)
2. 4칸 채움: **Why / Scope / 설계 / 완료 조건**
   - 모호한 요구사항은 추정하지 말고 먼저 질문해서 채운다
3. 완료 조건(Acceptance Criteria)이 곧 **루프 종료 기준**이 된다
4. 구현 → 완료 조건 체크리스트로 검증

## 규칙

- Spec 상태는 파일 맨 위 한 줄(`Draft → Implemented`)로만 표시. 별도 상태표 관리 안 함 (git 히스토리로 충분).
- 완료된 Spec도 그냥 `docs/specs/`에 둔다 (이동·정리 불필요).
- 빈 칸 채우기 강요 안 함 — 해당 없으면 "없음"이라고만 적고 넘어간다.

## 반복되는 함정 (Lessons Learned)

구현 전에 한 번씩 확인:

| 함정 | 대응 |
|------|------|
| `result-layout` grid 깨짐 | 새 요소에 `grid-column`/`grid-row` 명시 |
| `InFailedSqlTransaction` 500 | pgBouncer는 쿼리 실패 시 `except`에서 `conn.rollback()` 필수 |
| 신규 컬럼 `UndefinedColumn` | Supabase에 `ALTER TABLE` 수동 실행 필요 (스키마 파일만 고치면 안 됨) |
| 504 Timeout (넓은 가격범위) | 매칭 단지 폭증 → ODsay 셀 수 급증. `min_price` 필터로 제한 |
| `result.html` 새 HTML 추가 | `.result-layout` grid 자식 구조 영향 확인 |
