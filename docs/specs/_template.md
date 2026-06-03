# Spec: [Feature Name]

> **상태**: Draft / In Review / Approved / Implemented  
> **작성일**: YYYY-MM-DD  
> **구현 브랜치**: hjkang83/[feature-name]

---

## 1. Why (왜 만드는가)

- MANIFESTO의 어떤 원칙을 구현하는가:
  > 예: "비교가 판단을 만든다" → 버킷별 최저가 비교를 더 명확하게 보여줌
- 사용자가 얻는 가치:
- Why Tree 계층 연결 (개인화된 추천 / 신뢰할 수 있는 데이터 / 이해하기 쉬운 설명):

---

## 2. User Story

```
As a [직장인 / 신혼부부 / 투자자 등],
I want to [무엇을 하고 싶은가],
so that [어떤 이익을 얻는가].
```

---

## 3. Scope

### In-scope
- 포함되는 기능들

### Out-of-scope (Non-goals)
- 의도적으로 제외하는 것들과 이유

---

## 4. Functional Requirements

- F1.
- F2.
- F3.

---

## 5. Non-functional Requirements

- **성능**: 응답시간 < Xms (Vercel 60초 제약 감안)
- **보안**: (인증 필요 여부, 입력 검증 수준)
- **신뢰성**: 에러 시 사용자에게 어떻게 표시하는가
- **호환성**: 모바일 / 데스크톱 / 브라우저

---

## 6. UX / Vibe

MANIFESTO에서 전달해야 할 정서:
> 예: "카톡 한 줄" 톤 — 분석 리포트가 아닌 친구의 한마디

- 톤:
- 색상/인터랙션 가이드:
- 에러 메시지 톤: (기술적 오류 메시지 X, 친근한 안내 O)

---

## 7. Data Model

```
엔티티명
├── field_name: type  -- 설명
├── field_name: type
└── ...

관계:
- A → B (1:N)
```

영향받는 테이블: `table_name`, `table_name2`

---

## 8. API / Interface

```python
# 엔드포인트 또는 함수 시그니처

POST /api/[endpoint]
Request:
  {
    "field": type,  # 설명
  }
Response:
  {
    "field": type,
  }
```

---

## 9. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| 빈 결과 | |
| 네트워크 오류 | |
| 잘못된 입력 | |
| Vercel 60초 초과 | |
| Supabase 연결 실패 | |

---

## 10. Acceptance Criteria

구현 완료 판단 기준 (체크리스트):

- [ ] AC1:
- [ ] AC2:
- [ ] AC3:
- [ ] 모바일에서 정상 동작
- [ ] 에러 케이스에서 사용자 친화적 메시지 노출
- [ ] 로컬(SQLite) + Vercel(Supabase) 양쪽 환경에서 동작

---

## 11. Open Questions

- Q1: (결정 필요한 사항)
- Q2:

---

## 12. 구현 메모 (Implement 후 채우기)

- 변경된 파일:
- 주요 결정 사항:
- 알려진 제약:
