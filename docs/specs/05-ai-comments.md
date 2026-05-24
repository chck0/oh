# Spec: AI 코멘트 생성 (Claude LLM)

> **상태**: Implemented  
> **구현 파일**: `app/ai.py` — `build_comments()`, `build_recommend_comments()`, `build_regular_comments()`  
> **작성일**: 2026-05-24 (retrospective)

---

## 1. Why

MANIFESTO — "직장 주소 하나를 넣으면, 친구처럼 솔직하게 말해준다."  
수치만 나열하면 사용자는 비교를 포기한다. LLM 코멘트로 판단 보조 (Why Tree #4).  
점수·가중치는 룰로 산출하므로 LLM은 자연어 표현에만 개입 → 할루시네이션 리스크 최소화.

---

## 2. User Story

```
As a result.html (카드 소비자),
I want to 각 카드에 "부동산 잘 아는 친구의 한마디"가 붙어 있으면,
so that 수치를 해석하는 부담 없이 핵심 장단점을 바로 이해한다.
```

---

## 3. Scope

### In-scope
- 추천 카드 → Claude Sonnet (2문장, 최대 80자, 장단점 균형)
- 일반 카드 → Claude Haiku (1문장, 40자 이내)
- Sonnet 실패 시 Haiku 폴백
- DB 캐시 (apt_pt_friend_comment 테이블) — 같은 (apt_seq, pyeong_type, wp_id) 재호출 없음
- BackgroundTasks로 비동기 생성 (API 응답 지연 없음)

### Out-of-scope
- 스트리밍 응답
- 코멘트 사용자 피드백 (좋아요/싫어요)
- 다국어 코멘트
- 프롬프트 A/B 테스트 자동화

---

## 4. Functional Requirements

- F1. 추천 카드 (`is_recommended=True`) → Sonnet 호출
  - 프롬프트: 단지명, 평형, 가격, 통근시간, 연식, 세대수, 평균 대비 %
  - 출력: 2문장 카톡 톤, 80자 이내, 이모지 X, 장점 1 + 단점 1
- F2. 일반 카드 → Haiku 호출
  - 프롬프트: 단지명, 평형, 통근, 가격, 연식 한 줄
  - 출력: 1문장, 40자 이내, 반말
- F3. 일반 카드 동시 호출 8개 제한 (Semaphore)
- F4. 추천/일반 asyncio.gather로 병렬 처리
- F5. 결과 `apt_pt_friend_comment` 테이블에 upsert 캐시
- F6. 캐시 히트 시 LLM 미호출, 즉시 반환
- F7. `llm_pending=true` 시 result.html이 폴링으로 완료 확인

---

## 5. Non-functional Requirements

- **비용**: 추천 카드(소수) → Sonnet, 일반(다수) → Haiku로 비용 최적화
- **속도**: BackgroundTasks로 비동기 — API 응답 차단 없음
- **Rate limit**: 일반 카드 동시 8개 이하 (Anthropic 안전치)
- **폴백**: Sonnet 실패 → Haiku 재시도

---

## 6. UX / Vibe

MANIFESTO — "카톡 한 줄"

프롬프트 톤 규칙:
- "~야", "~네", "~겠다" 자연스러운 반말
- 보고서 표현 금지: "고려할 만하고", "감안하면", "검토해야"
- 수치 1개씩만 인용 (장점 1 + 단점 1)
- 이모지·따옴표 X

좋은 예: "25분에 4억이면 진짜 싸. 근데 27년차 구축이라 인테리어 한 번은 해야 할 거야."  
나쁜 예: "이 단지는 가격 경쟁력이 확실하지만 연식이 오래되어 리모델링 시점 확인이 필요하고..."

---

## 7. Data Model

**캐시 테이블 `apt_pt_friend_comment`**

| 컬럼 | 타입 | 설명 |
|---|---|---|
| apt_seq | TEXT | 단지 ID |
| pyeong_type | TEXT | 평형 |
| wp_id | INTEGER | 직장 ID |
| comment | TEXT | 생성된 코멘트 |
| model | TEXT | 사용 모델명 |
| created_at | TEXT | 생성 시각 |
| PK | (apt_seq, pyeong_type, wp_id) | |

---

## 8. API / Interface

```python
# 통합 진입점
await build_comments(
    target_cards: list[dict],   # 코멘트 생성 대상
    all_cards: list[dict],       # 평형별 평균가 계산용
    wp_label: str                # 프롬프트 컨텍스트용
) -> dict[str, dict]             # card_key → {comment, kind}

# 내부 분리
await build_recommend_comments(...)  # Sonnet
await build_regular_comments(...)    # Haiku
```

폴링 엔드포인트:

```
GET /api/apt/{apt_seq}/comment?wp_id={wp_id}&pyeong_type={pt}
Response: { "comment": "...", "done": true/false }
```

---

## 9. Edge Cases

| 케이스 | 현재 동작 |
|---|---|
| Sonnet 호출 실패 | Haiku 폴백 재시도 |
| Haiku도 실패 | `"(생성 실패)"` 반환 |
| 캐시 있음 | LLM 미호출, 즉시 반환 |
| 카드 0개 | 빈 dict 반환, 호출 없음 |
| rate limit 초과 | 동시 8개 Semaphore가 줄 세움 |
| 카드 1개 프롬프트 생성 예외 | `return_exceptions=True`로 해당 카드만 실패, 나머지 정상 반환 |

---

## 10. Acceptance Criteria

- [x] 추천 카드 Sonnet 2문장 코멘트 생성
- [x] 일반 카드 Haiku 1문장 코멘트 생성
- [x] Sonnet 실패 시 Haiku 폴백
- [x] 생성 결과 DB 캐시, 재검색 시 재호출 없음
- [x] 동시 호출 8개 이하 제한
- [x] BackgroundTasks로 API 응답 차단 없음

---

## 11. 개선 아이디어 (Open)

- 프롬프트 버전 관리 + A/B 테스트 (model 컬럼 활용)
- 코멘트 품질 주기적 샘플링
- 추천 카드 코멘트를 더 짧게 (현재 2문장 → 1.5문장 느낌 목표)
- 캐시 만료 정책 (예: 30일 후 재생성)
