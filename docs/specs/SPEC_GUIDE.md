# BADUGI Spec 작성 가이드

> 코드는 Spec의 번역물입니다. Spec이 모호하면 코드도 모호하고,
> Spec이 정확하면 AI는 놀라울 만큼 정확한 코드를 만듭니다.

---

## 왜 Spec이 먼저인가

BADUGI는 "부동산 잘 아는 친구가 카톡으로 추천해주는" 서비스입니다.
이 톤과 철학이 코드에 스며들려면, 코드를 짜기 전에 **무엇을 왜 어떻게** 만들지 명문화해야 합니다.

Spec 없이 구현하면:
- 중간에 요구사항이 바뀌어 롤백 비용이 커진다
- AI가 잘못된 방향으로 코드를 쌓는다
- 완성 후에 "이게 아닌데"가 나온다

Spec이 있으면:
- AI와의 대화가 정확해진다
- 리뷰 단계에서 빠진 케이스를 미리 잡는다
- 구현이 끝난 뒤 Acceptance Criteria로 검증할 수 있다

---

## 작업 흐름

```
1. Interview  →  AI가 질문, 나는 답변
2. Spec 작성  →  AI가 초안, 나는 한 줄씩 읽고 수정
3. Review     →  에이전트 팀 소집 → 비평 → 결정 → 반영
4. Implement  →  Spec 기반 코드 생성
5. Test       →  AC 체크리스트로 검증 → 오류 → AI에 붙여넣기 → 반복
```

---

## Step 1 — Interview (AI에게 요청)

```
[Feature Name]에 대한 Spec을 작성하기 전에, 
BADUGI MANIFESTO.md의 가치와 일치하는지 확인하면서 
빠진 부분을 채울 수 있도록 인터뷰해줘.
```

AI가 묻는 전형적인 질문 유형:

| 카테고리 | 질문 예시 |
|---|---|
| User | 누가 사용하는가? 어떤 상황에서? |
| Problem | 지금 무엇이 불편한가? |
| Success Criteria | 무엇이 달라지면 성공인가? |
| Constraints | 기술·시간·비용 제약은? |
| Non-goals | 의도적으로 제외할 것은? |
| Data Model | 어떤 데이터를 다루는가? |
| UX Flow | 사용자 동선은 어떻게 되는가? |

---

## Step 2 — Spec 초안 작성

파일 위치: `docs/specs/[feature_name].md`

`_template.md`를 복사해서 시작합니다.

```bash
cp docs/specs/_template.md docs/specs/[feature_name].md
```

---

## Step 3 — Spec 읽기 (가장 중요)

생성된 Spec을 한 줄씩 읽으면서 자문합니다:

- ❓ 이게 정말 내가 원하는 것인가?
- ❓ [MANIFESTO](../manifesto.md)의 가치와 일치하는가?
- ❓ AI가 잘못 가정한 부분은 없는가?
- ❓ 빠진 엣지케이스는 없는가?
- ❓ [Pre-mortem](../premortem.md)의 위험 시나리오를 악화시키지 않는가?

---

## Step 4 — Review (에이전트 팀 소집)

```
docs/specs/[feature_name].md 를 검토해서 
개선이 필요한 부분을 비평해줘. 
서로 충돌하는 제안이 있으면 내가 결정할 수 있도록 물어봐.
```

리뷰 사이클:
1. 에이전트 비평 받기
2. 충돌 제안 → 직접 결정
3. 결정 사항을 Spec에 반영
4. 동일 에이전트 재검토 요청

---

## Step 5 — Implement

```
docs/specs/[feature_name].md 를 기반으로 구현해줘.
인프라 설정이 필요하면, 단계별 지침과 이유를 함께 알려줘.
```

---

## Step 6 — Test

- Acceptance Criteria 체크리스트로 수동 검증
- 에러 발생 시 → 에러 메시지 전체를 AI에 붙여넣기
- "느낌이 이상하면" → Spec 단계로 돌아가서 업데이트

```
Test → Error → 에러 붙여넣기 → AI 수정 → Re-test
     │
     └─ "느낌이 이상함" → Spec 재작성
```

---

## 좋은 Spec 프롬프트 vs 나쁜 Spec 프롬프트

| ❌ 나쁜 예 | ✅ 좋은 예 |
|---|---|
| "검색 페이지 개선해줘" | "MANIFESTO의 '비교가 판단을 만든다' 원칙에 따라, 검색 결과에서 버킷별 요약 통계를 보여주는 기능의 Spec을 작성해줘. 인터뷰해줘." |
| "DB 설계해줘" | "transit_cache 테이블의 만료 정책 Spec을 작성해줘. 제약: Supabase Postgres + pgBouncer Transaction mode. 빠진 게 있으면 인터뷰해줘." |
| "AI 코멘트 바꿔줘" | "MANIFESTO의 '카톡 한 줄' 톤을 유지하면서 Haiku 코멘트 품질을 높이기 위한 프롬프트 개선 Spec을 써줘. 인터뷰해줘." |

---

## BADUGI Spec 체크리스트

Spec 완성 전 확인:

- [ ] MANIFESTO.md의 어떤 원칙을 구현하는가 명시됨
- [ ] Why Tree의 기존 결정과 충돌하지 않음
- [ ] Pre-mortem의 위험 시나리오를 악화시키지 않음
- [ ] Non-goals에 의도적 제외 항목이 명시됨
- [ ] Acceptance Criteria가 체크리스트 형태로 작성됨
- [ ] Vercel 60초 제약 / Supabase pgBouncer 제약 반영됨
- [ ] 모바일 UX 고려 여부 명시됨

---

## 기존 Specs

| 파일 | 기능 | 상태 |
|---|---|---|
| [01-search-input.md](01-search-input.md) | 검색 조건 입력 화면 (search.html) | Implemented |
| [02-search-pipeline.md](02-search-pipeline.md) | 검색 파이프라인 (POST /api/search) | Implemented |
| [03-recommendation-engine.md](03-recommendation-engine.md) | 추천 엔진 (통근버킷 × 평형 매트릭스) | Implemented |
| [04-result-page.md](04-result-page.md) | 검색 결과 화면 (result.html) | Implemented |
| [05-ai-comments.md](05-ai-comments.md) | AI 코멘트 생성 (Claude LLM) | Implemented |

새 Spec 추가 시 이 표를 업데이트하세요.
