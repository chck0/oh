# Spec 24: 친구 채팅 v3 — 호가 링크 · 동적 Chip · 웹 검색

> **상태**: In Progress 🔨
> **작성일**: 2026-05-30
> **구현 브랜치**: hjkang83

---

## 1. Why (왜 만드는가)

spec-23에서 컨텍스트·캐시를 개선했지만 세 가지 사용자 페인포인트가 남음:
1. **호가 공백**: 실거래 데이터는 있지만 현재 매물 호가(네이버·호갱노노)로 바로 이동할 방법 없음
2. **정적 Chip**: 대화 맥락과 무관한 고정 질문 5개 → 무관한 질문이 UI를 차지
3. **학군·개발계획 공백**: Claude가 외부 실시간 정보에 답하지 못해 "모른다" 남발

---

## 2. Scope

### In-scope
- **F1 호가 링크**: 채팅 패널 상단에 네이버부동산·호갱노노 검색 URL 버튼
- **F2 동적 Chip**: 매 응답 후 Claude 생성 후속 질문 3개로 sugBox 갱신
- **F3 웹 검색**: DuckDuckGo Instant Answer API + Claude tool_use (API 키 불필요)

### Out-of-scope
- 호갱노노·네이버 내부 단지 ID 매핑 (검색 URL로 대체)
- 유료 검색 API (Tavily, SerpAPI 등) — 필요 시 `_do_search` 교체만으로 적용 가능
- 스트리밍 응답

---

## 3. Functional Requirements

### F1. 호가 링크 바 (프론트엔드)

채팅 패널 헤더 아래 고정 바:
```
[ 호가 보기: 네이버부동산 ]  [ 호갱노노 ]
```

두 플랫폼 모두 단지별 내부 ID 없이 직접 단지 페이지 연결 불가.
- **네이버부동산**: `https://new.land.naver.com/complexes?ms=37.5,127,13&a=APT:ABYG:JGC:DDDAPT&e=RETAIL&q={aptNm}` (지도+검색 열림)
- **호갱노노**: `https://hogangnono.com/` (홈 직접 연결 — `/apt/search` 경로 404 확인됨)
- 아실(`asil.kr`): 제외 — URL 구조 404 확인됨

### F2. 동적 Chip (백엔드 + 프론트엔드)

백엔드: 시스템 프롬프트에 지시 추가
```
답변 마지막에 공백 한 줄 후 반드시 아래 형식으로 한국어 후속 질문 3개 추가:
CHIPS: 질문1 | 질문2 | 질문3
```

파싱:
```python
chips_match = re.search(r'\nCHIPS:\s*(.+)$', raw, re.MULTILINE)
# suggestions = [q1, q2, q3], reply = raw 앞부분
```

응답: `{"reply": str, "suggestions": list[str]}`

프론트엔드: 수신 후 `data.suggestions`로 sugBox 즉시 갱신

### F3. 웹 검색 tool_use (백엔드)

도구 정의:
```python
{"name": "search_web", "description": "학군·지역정보·개발계획 실시간 검색", ...}
```

구현체: DuckDuckGo Instant Answer API (urllib, 타임아웃 5s)
```
https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1
```

agentic loop: 최대 3턴, tool_use → 검색 → tool_result → 최종 답변

---

## 4. Data Model

```
apt_chat 응답:
{
  "reply": str,           # 표시할 텍스트 (CHIPS 라인 제거됨)
  "suggestions": list[str]  # 0~3개
}
```

캐시: raw 텍스트(CHIPS 포함) 저장 → 조회 시 파싱

---

## 5. 구현 파일

| 파일 | 변경 |
|------|------|
| `app/search.py` | `_do_search()` 추가, `_parse_reply()` 추가, `apt_chat` tool_use 루프 + suggestions 반환 |
| `web/result.html` | 호가 링크 바 HTML·CSS·JS, `sendChatMessage` suggestions 처리, chip 클릭 핸들러 수정 |

---

## 6. Acceptance Criteria

- [ ] AC1: 채팅 패널 상단에 네이버부동산·호갱노노 링크 표시
- [ ] AC2: 메시지 수신 후 sugBox가 Claude 생성 후속 질문 3개로 갱신
- [ ] AC3: 학군·개발계획 질문 시 DuckDuckGo 검색 결과 포함 답변
- [ ] AC4: 기존 pytest 전체 통과 (회귀 없음)
