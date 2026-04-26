# /ship-stage — 현재 스테이지 완결 후 PR 머지

현재 작업 중인 스테이지를 완결하고 main에 머지하는 전체 플로우를 실행한다.

## 순서

1. `pytest tests/ -v` 전체 테스트 실행 — 실패 시 수정 후 재실행
2. `git diff --stat`으로 변경 파일 확인
3. conventional commit 메시지로 커밋 (feat:/fix:/refactor:/test:/docs:)
4. `git push -u origin <현재 브랜치>`
5. GitHub MCP로 PR 생성 (squash merge 기준)
6. PR 머지
7. 머지 결과 요약 보고

## 규칙

- 테스트가 전체 통과하지 않으면 절대 커밋하지 않는다
- 커밋 메시지는 한국어 또는 영어, 변경 내용을 정확히 반영
- PR body에 Summary + Test plan 포함
- push 실패 시 rebase 후 재시도 (최대 4회)
