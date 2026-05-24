# Spec: 검색 결과 화면

> **상태**: Implemented  
> **구현 파일**: `web/result.html`  
> **작성일**: 2026-05-24 (retrospective)

---

## 1. Why

MANIFESTO — "친구처럼 솔직하게 말해준다."  
검색 결과는 분석 리포트가 아닌 비교 가능한 카드들. 지도로 위치를 보고, 카드로 조건을 비교하고, AI 코멘트로 판단을 보조한다.

---

## 2. User Story

```
As a 직장인,
I want to 내 조건에 맞는 아파트 추천 카드와 지도, 통계를 한 화면에서 보고,
so that 어떤 단지가 통근시간과 가격 면에서 가장 합리적인지 빠르게 판단한다.
```

---

## 3. Scope

### In-scope
- URL 파라미터 → API 호출 → 결과 렌더링
- 로딩 오버레이 (3단계 진행 표시 → 완료 후 자동 전환)
- 좌측 패널: 통계 + 카드 리스트 (추천 먼저)
- 우측 패널: Kakao 지도 + 단지 핀
- 추천 카드 강조 + AI 코멘트
- LLM 코멘트 폴링 (llm_pending=true 시)
- partial 결과 amber 배너

### Out-of-scope
- 카드 즐겨찾기 / 비교 저장
- 거래 상세 차트 (별도 페이지 검토 중)
- 지도 경로 시각화

---

## 4. Functional Requirements

- F1. URL 파라미터 없음 시 `/search.html`로 redirect
- F2. 로딩 오버레이 3단계: "직장 위치 확인" → "경로 분석 중" → "매물 매칭"
- F3. API 응답 완료 후 1.2초 뒤 오버레이 자동 해제
- F4. 통계 패널: 총 매물 수, 평균가, 통근-가격 곡선 차트, 평형별 분포
- F5. 추천 카드: 버킷 그룹별로 묶어 표시, "추천" 배지 + pick_reason
- F6. 일반 카드: 추천 카드 하단에 펼쳐서 표시
- F7. 카드 항목: 단지명, 평형, 통근시간, 실거래가(최저~최고), AI 코멘트
- F8. 지도: Kakao Maps, 단지 위치 핀, 직장 위치 핀, 클릭 시 카드 하이라이트
- F9. llm_pending=true 시 폴링 시작
  - 최대 72회 (약 6분 후 자동 종료)
  - `document.hidden` 시 15초 간격 (탭 비활성화 최적화)
- F10. partial=true 시 amber 배너 "일부 경로 데이터 수집 중, 잠시 후 재검색"

---

## 5. Non-functional Requirements

- **성능**: API 응답 수신 후 렌더링 < 500ms
- **모바일**: 지도/카드 패널 세로 배치, 지도 높이 고정
- **안정성**: 폴링 최대 72회 후 자동 종료 (무한루프 방지)

---

## 6. UX / Vibe

MANIFESTO — "카톡 한 줄"  
AI 코멘트는 카드 내 회색 말풍선 스타일. 기다리는 동안 skeleton 표시.  
추천 카드는 배경색 강조 (brand-bg-subtle). 로딩 오버레이는 단계별 체크마크.

---

## 7. Data Model

URL 파라미터로 입력받아 `POST /api/search` 호출.  
응답 JSON → 로컬 변수 `resultData`에 저장 후 렌더링.

**카드 핵심 필드**

| 필드 | 표시 |
|---|---|
| apt_nm, umd_nm | 단지명, 동 |
| total_time_min | 통근시간 |
| price_low, price_high | 실거래가 범위 |
| pyeong_type | 평형 |
| is_recommended | 추천 배지 |
| pick_reason | 추천 사유 |
| friend_comment | AI 코멘트 |
| kaptdaCnt | 세대수 |
| use_date, build_year | 준공연도 |

---

## 8. API / Interface

```javascript
// 검색
POST /api/search  ← URL 파라미터 JSON으로 변환

// 코멘트 폴링
GET /api/apt/{apt_seq}/comment?wp_id={wp_id}&pyeong_type={pt}
→ { comment: string, done: boolean }
```

---

## 9. Edge Cases

| 케이스 | 현재 동작 |
|---|---|
| URL 파라미터 누락 | `/search.html` redirect |
| cards 빈 배열 | "조건에 맞는 매물이 없어요" 빈 상태 |
| API 500 오류 | 에러 메시지 표시 |
| partial=true | amber 배너 표시 |
| llm_pending 72회 초과 | 폴링 자동 종료, 코멘트 미표시 |
| 탭 비활성화 중 폴링 | 15초 간격으로 느리게 |

---

## 10. Acceptance Criteria

- [x] URL 파라미터 없으면 search.html redirect
- [x] 로딩 오버레이 3단계 표시 후 자동 전환
- [x] 추천 카드 배지 + pick_reason 표시
- [x] Kakao 지도 단지 핀 + 직장 핀
- [x] llm_pending 시 폴링 (최대 72회)
- [x] partial=true amber 배너
- [x] 모바일 반응형

---

## 11. 개선 아이디어 (Open)

- 카드 필터/정렬 UI (통근시간순, 가격순)
- 지도 클릭 → 해당 카드 자동 스크롤
- 최근 거래 내역 미니 테이블 (평형·층·거래가·날짜)
- 모바일 지도/리스트 토글 버튼
- 결과 공유 링크 (URL 그대로 공유 가능)
