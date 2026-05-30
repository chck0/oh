# Spec 26: 분석결과 아파트 직접 검색

> **상태**: In Progress 🔨
> **작성일**: 2026-05-30
> **구현 브랜치**: hjkang83

---

## 1. Why

추천 결과에 원하는 아파트가 없을 때 직접 이름으로 검색해 시세·통근시간을 확인하고 싶은 니즈.
현재는 검색 조건을 바꿔 재검색하거나 아예 나가야 함 → 이탈 원인.

---

## 2. Scope

### In-scope
- 분석결과 화면(result.html) 추천 목록 바로 위 검색 인풋
- 아파트 이름 키워드 검색 → 최대 3개 후보 표시
- 후보 선택 시 단지 정보 카드(가격·통근시간·세대수) 표시
- 채팅 버튼 포함 (친구 채팅 바로 열기)

### Out-of-scope
- 검색 결과의 지도 핀 표시
- 검색 결과의 즐겨찾기 저장

---

## 3. Functional Requirements

### F1. 검색 인풋 (프론트엔드)

`renderCards` 내 `rec-section-head` 바로 앞에 삽입:
```html
<div class="apt-search-bar">
  <input id="apt-search-input" placeholder="아파트 이름으로 직접 검색…" maxlength="30">
  <button onclick="searchAptDirect()">찾기</button>
</div>
<div id="apt-search-result"></div>
```

Enter 키 지원, 2글자 미만 입력 시 무시.

### F2. 백엔드 엔드포인트

`GET /api/search/apt-lookup`

파라미터:
- `name: str` — 아파트 이름 키워드
- `wp_id: int` — 직장 ID (통근시간 캐시 조회용)
- `pyeong_type: str = "20평대"` — 가격 조회 평형

응답:
```json
{
  "results": [
    {
      "apt_seq": "...",
      "apt_nm": "래미안아트리치",
      "umd_nm": "서초동",
      "lat": 37.49,
      "lng": 127.01,
      "kaptdaCnt": 832,
      "build_year": 2008,
      "pyeong_type": "20평대",
      "price_low": 85000,
      "price_high": 92000,
      "transit_min": 28
    }
  ]
}
```

쿼리 로직:
1. `apartments WHERE apt_nm LIKE %name% AND is_apt=1 ORDER BY kaptdaCnt DESC LIMIT 3`
2. 각 단지: `trade_recent`에서 `pyeong_type` 최저·최고가 조회
3. 통근시간: `transit_cache JOIN apartments` 로 캐시된 최소값 조회

### F3. 결과 카드 (프론트엔드)

추천 카드와 유사한 스타일, 상단에 "직접 검색" 배지:
```
┌─────────────────────────────────┐
│ [직접 검색] 래미안아트리치       │
│ 서초동 · 832세대 · 2008년       │
│ 20평대  85,000~92,000만원        │
│ 통근 28분                        │
│                         [친구]   │
└─────────────────────────────────┘
```

---

## 4. 구현 파일

| 파일 | 변경 |
|------|------|
| `app/search.py` | `GET /api/search/apt-lookup` 엔드포인트 추가 |
| `web/result.html` | 검색 인풋 CSS + HTML + JS (`searchAptDirect`, `renderAptLookupCard`) |

---

## 5. Acceptance Criteria

- [ ] AC1: 결과 화면 추천 목록 위에 검색 인풋 표시
- [ ] AC2: 아파트 이름 검색 시 최대 3개 후보 카드 표시
- [ ] AC3: 카드에 가격·통근시간·세대수 표시 (데이터 없으면 "-")
- [ ] AC4: 카드의 친구 버튼 클릭 시 채팅 패널 열림
- [ ] AC5: 기존 pytest 387+ passed 유지
