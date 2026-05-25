# Spec: 관심 단지 ♥ 즐겨찾기 (favorites)

> **상태**: In Progress 🚧  
> **작성일**: 2026-05-25  
> **구현 브랜치**: hjkang83

---

## 1. Why (왜 만드는가)

- 사용자 인터뷰: "마음에 드는 단지를 따로 표시해두고 싶어요" — 검색할 때마다 다시 찾는 불편함
- 현재 결과 페이지에는 북마크 수단이 전혀 없어 "좋은 단지" 정보가 새로고침 시 사라짐
- 즐겨찾기 단지만 모아보는 필터가 있으면 비교 검토 흐름이 자연스러워짐
- localStorage 기반이라 백엔드 변경 없이 즉시 구현 가능

---

## 2. User Story

```
As a 아파트 비교 중인 사용자,
I want to  카드에 하트(♥)를 눌러 관심 단지를 저장하고,
so that    나중에 검색 결과에서 내가 찜한 단지만 빠르게 볼 수 있다.
```

---

## 3. Scope

### In-scope
- 추천 카드 / 리스트 카드에 ♥ 버튼 추가 (토글)
- localStorage key `badugi_favorites` 에 `apt_seq:pyeong_type` Set 저장
- 결과 페이지 상단 탭: **전체** / **♥ 관심 단지** 탭 전환
- 관심 단지 탭 선택 시 하트 표시된 카드만 필터링 (지도 핀도 동기화)
- 페이지 로드 시 localStorage에서 복원 → 카드 렌더링 시 하트 상태 반영

### Out-of-scope
- 서버 측 저장(DB): localStorage만 사용, 로그인 없음
- 관심 단지 순서 정렬·메모 기능
- 모바일 별도 UI: 기존 카드 레이아웃 그대로

---

## 4. Functional Requirements

### F1. ♥ 버튼
- 각 카드 우측 상단에 `♥` 아이콘 버튼 배치
- 찜 안 됨: `♡` (빈 하트, color: #ccc)
- 찜 됨: `♥` (꽉 찬 하트, color: #e74c3c)
- 클릭 시 토글 → localStorage 즉시 갱신 → 탭 카운트 업데이트

### F2. localStorage 스키마
```javascript
// key: 'badugi_favorites'
// value: JSON.stringify(['APT001:20평대', 'APT002:30평대', ...])
const FAV_KEY = 'badugi_favorites';

function loadFavs()  { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
function saveFavs(s) { localStorage.setItem(FAV_KEY, JSON.stringify([...s])); }
function favId(aptSeq, pyeongType) { return `${aptSeq}:${pyeongType}`; }
```

### F3. 탭 UI
- 결과 카드 목록 상단에 탭 2개:
  - `전체 (N)` — 기본 선택, 전체 카드 표시
  - `♥ N` — 관심 단지만 표시. N=0 이면 비활성(클릭 불가) + "아직 관심 단지가 없어요" 안내
- 탭 전환 시 카드 목록 + 지도 핀 동기화

### F4. 지도 핀 연동
- 관심 탭 선택 시 관심 단지 핀만 지도에 표시 (비관심 핀 숨김)
- 전체 탭 복귀 시 전체 핀 복원

---

## 5. Data Model

신규 테이블/컬럼 없음. localStorage만 사용.

```
localStorage['badugi_favorites'] = '["APT001:20평대","APT002:30평대"]'
```

---

## 6. Edge Cases

| 케이스 | 기대 동작 |
|--------|---------|
| localStorage 비어있음 | 관심 탭 카운트 0, 버튼 비활성 |
| 검색 조건 바뀐 후 재검색 | 이전 하트 상태 유지 (localStorage 기반) |
| 관심 단지가 새 검색 결과에 없음 | 해당 카드 없으므로 탭 카운트 자동 감소 |
| localStorage 용량 초과 | try/catch 로 silently ignore |

---

## 7. Acceptance Criteria

- [ ] **AC1**: ♥ 버튼 클릭 시 localStorage에 저장되고 하트 색상 변경
- [ ] **AC2**: 페이지 새로고침 후에도 하트 상태 유지
- [ ] **AC3**: "♥ N" 탭 클릭 시 관심 단지만 카드 표시
- [ ] **AC4**: 관심 탭에서 지도 핀도 관심 단지만 표시
- [ ] **AC5**: 관심 단지 0개 시 탭 버튼 비활성 + 안내 문구 표시

---

## 8. 구현 메모

> **구현 중** (Loop 3회 예정)

### 변경 파일 예정

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `web/result.html` | 수정 | ♥ 버튼, localStorage 로직, 탭 UI, 지도 핀 연동 |
| `docs/specs/08-favorites.md` | 수정 | AC 체크 + 구현 메모 업데이트 |
