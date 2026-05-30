# Spec 23: 친구 채팅 고도화

> **상태**: In Progress 🔨
> **작성일**: 2026-05-30
> **구현 브랜치**: hjkang83

---

## 1. Why (왜 만드는가)

spec-22에서 기본 채팅을 구현했지만 세 가지 한계가 있음:
1. **정확도 부족**: 실거래 20건만 제공 — 동 평균·시세 트렌드 없어 "호가 얼마야?" 같은 질문에 맥락 부족
2. **성능 비효율**: 동일 단지에 동일 질문을 반복해도 매번 Claude Opus 호출 (비용 낭비)
3. **UX 단절**: 페이지 새로고침 시 대화 내역 초기화 → 이전 대화 맥락 손실

---

## 2. Scope

### In-scope
- **컨텍스트 강화**: 시스템 프롬프트에 동 평균가·6개월 변동률·평형별 통계 추가
- **인메모리 캐싱**: (apt_seq, 질문, history_len) 키 기준 1시간 TTL 캐시
- **localStorage 대화 유지**: 단지별 대화 기록 24시간 브라우저 저장/복원

### Out-of-scope
- DB 기반 영구 채팅 저장
- 실시간 호가 외부 API 연동
- 스트리밍 응답

---

## 3. Functional Requirements

### F1. 컨텍스트 강화 (백엔드)

시스템 프롬프트에 추가:

```
== 시세 통계 (1년 기준) ==
- 30평대: 평균 11.2억 / 최저 10.1억 / 최고 13.5억 / 거래 26건
- 20평대: 평균 7.8억 / 최저 7.0억 / 최고 8.9억 / 거래 14건

== 6개월 시세 변동 ==
- 30평대: +3.2% (최근 3개월 avg vs 이전 3개월 avg)

== 동 평균 시세 (30평대, 최근 6개월) ==
- 녹번동 30평대: 평균 10.8억
```

### F2. 인메모리 캐싱 (백엔드)

```python
_chat_cache: dict = {}  # module-level
# key: (apt_seq, hash(message), history_len)
# value: (timestamp: float, reply: str)
CACHE_TTL = 3600  # 1시간
```

- history_len <= 2인 경우만 캐시 (초기 질문만, 맥락 이어지는 질문 제외)
- 캐시 히트 시 Claude 호출 없이 즉시 반환
- 오래된 캐시 자동 정리 (호출 시 만료된 항목 제거)

### F3. localStorage 대화 유지 (프론트엔드)

```javascript
// 저장: 채팅 패널 닫거나 메시지 받을 때
localStorage.setItem(`chat_${apt_seq}`, JSON.stringify({
  ts: Date.now(),
  history: _chatHistory.slice(-10),
}));

// 복원: openFriendChat 시
const saved = localStorage.getItem(`chat_${apt_seq}`);
if (saved && Date.now() - JSON.parse(saved).ts < 86400000) {
  _chatHistory = JSON.parse(saved).history;
}
```

- 단지별로 저장 (키: `chat_{apt_seq}`)
- 최대 10턴 저장, 24시간 TTL

---

## 4. Acceptance Criteria

- [x] **AC1**: 시스템 프롬프트에 동 평균가·변동률·평형 통계 포함
- [x] **AC2**: 동일 질문(history_len<=2) 재질문 시 캐시에서 응답 (< 100ms)
- [x] **AC3**: 채팅 후 새로고침 → 동일 단지 채팅 재진입 시 이전 대화 복원
- [x] **AC4**: 387 tests passed (회귀 없음)

---

## 5. 구현 메모

| 파일 | 변경 |
|------|------|
| `app/search.py` | `_chat_cache` 모듈 변수, `apt_chat` 컨텍스트 강화 + 캐시 로직 |
| `web/result.html` | `openFriendChat` localStorage 복원, `_appendChatMsg` 저장 호출 |
