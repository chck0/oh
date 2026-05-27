# Spec 13 — 맞벌이 두 직장 교집합 추천 (Dual Workplace)

**상태:** ✅ Implemented
**작성일:** 2026-05-26
**최종수정:** 2026-05-26
**구현 브랜치:** hjkang83
**관련 spec:** 01 (search-input), 02 (search-pipeline), 03 (recommendation-engine), 04 (result-page), 05 (ai-comments), 11 (rec-card-emphasis)

---

## 1. Why

- **MANIFESTO 원칙**: "통근은 삶의 질이다. 집값보다 출퇴근 시간이 행복에 더 큰 영향을 미친다. 모든 추천의 첫 번째 축은 통근시간이다."
  → 가족 단위 의사결정에서 **한 사람의 통근만 고려하면 다른 사람이 희생**된다. 두 통근을 동시에 만족시키는 단지를 찾는 것이 핵심.

- **사용자 피드백 시그널**: 40여 명 인터뷰 중 **6명이 명시적으로 요청** (가장 강한 합의):
  - "남편이든 나든 직장 둘 다 입력하고 싶어요"
  - "맞벌이 부부 기준 검색 기능 필요"
  - "양쪽 직장 모두 통근 가능한 단지"

- **경쟁 우위 (Moat)**: 네이버부동산·호갱노노·직방·다방 어디에도 "두 직장 교집합" 기능 제공 없음. **BADUGI 차별점 핵심**.

- **Why Tree 연결**: #1 "왜 직장 주소를 입력 기준으로 일반화?"의 확장 → 직장 1개 → 가족 단위 직장 2개로 자연스럽게 확장. 매니페스토 100% 정렬.

---

## 2. User Story

```
As a 맞벌이 부부 (또는 두 직장 가족),
I want to 우리 두 사람의 직장 주소를 모두 입력하고,
so that 두 사람의 통근시간이 동시에 합리적인 단지만 추천받아,
   한 사람의 통근만 좋은 단지에 결정하는 비용을 줄일 수 있다.
```

부수적 사용 시나리오:
- 1인 직장: 기존 single workplace 모드 그대로 (회귀 없음)
- 부부 둘 다 입력: dual workplace 모드 활성화
- 부부 + 자녀 학교: out-of-scope (3개 이상 → 별도 spec)

---

## 3. Scope

### In-scope

- **A. 검색 입력 UI**: 직장 #1 (기존) + 직장 #2 (선택) 입력란. `+ 다른 가족 직장 추가` 한 줄 버튼으로 점진적 노출
- **B. 백엔드 API 확장**: `SearchRequest.workplace_address_2: str | None`. 두 워크플레이스 각각 `get_or_create()` → `wp_id`, `wp_id_2`
- **C. 추천 로직 확장**: 카드의 `total_time_min` = `max(t1, t2)`. `build_recommendations()` 이 값으로 버킷 분류·매트릭스 추천 동일
- **D. 카드 응답 확장**: `total_time_min_2`, `transit_summary_2`, `bus_cnt_2`, `subway_cnt_2` 신규 필드
- **E. UI 결과 화면**: 추천 칩 1 → `W1 25분 · W2 32분`, 지도 W2 파란 핀, summary bar 두 직장 표시
- **F. 캐시 효율 + 동적 분배**: ODsay 200셀 한도를 wp별 미스 수 측정 후 동적 분배
- **G. 교집합 0건 안내**: 두 직장 거리가 너무 멀어 결과 0건 시 친구 톤 메시지

### Out-of-scope

- ❌ 3인 이상 직장
- ❌ 가중치 (한 사람 통근을 N배 가중)
- ❌ 학교/어린이집 위치 고려
- ❌ 두 직장 사이 중간점 추천
- ❌ 사용자 라벨 입력 ("내" / "남편") — W1/W2 고정 (향후 enhancement)
- ❌ 친구 코멘트(Sonnet) dual 프롬프트 — spec-05 소관 (이번 spec 미포함)
- ❌ 즐겨찾기 dual 키 — `(apt_seq, pyeong_type)` 기준 그대로

---

## 4. Functional Requirements

### F1. SearchRequest 확장

```python
class SearchRequest(BaseModel):
    workplace_address: str = Field(..., min_length=2, max_length=200)
    workplace_address_2: str | None = Field(
        None, min_length=2, max_length=200,
        description="두 번째 직장 주소 (맞벌이용, 선택)"
    )
    max_minutes: int = Field(60, ge=10, le=60)
    max_price: int = Field(50000, ge=1000, le=2_000_000)
    pyeong_types: list[str]
    min_kaptdaCnt: int | None = None
    build_year_min: int | None = None
    min_price: int | None = None

    @field_validator('workplace_address_2')
    @classmethod
    def _check_workplace_2(cls, v, info):
        if v is not None:
            wp1 = info.data.get('workplace_address', '').strip()
            if v.strip() == wp1:
                raise ValueError('두 직장이 동일합니다. 단일 모드로 검색하세요.')
        return v
```

### F2. wp_2 발급 및 좌표 확보

```python
wp_2 = None
if req.workplace_address_2:
    wp_2 = await asyncio.to_thread(get_or_create, conn, req.workplace_address_2)
    if not wp_2:
        raise HTTPException(400, f'두 번째 주소 변환 실패: {req.workplace_address_2}')
    if wp_2['wp_id'] == wp['wp_id']:
        raise HTTPException(422, '두 직장이 동일합니다. 단일 모드로 검색하세요.')
dual = wp_2 is not None
```

### F3. 후보 단지 필터링 → 두 wp 반경 교집합

dual 모드: 두 wp **모두** 반경 내 단지만 후보로 선정.

```python
near_keys = [
    a['apt_seq'] for a in apts
    if haversine(a['lat'], a['lng'], wp['lat'], wp['lng']) <= radius_km
    and (not dual or haversine(a['lat'], a['lng'], wp_2['lat'], wp_2['lng']) <= radius_km)
]
```

### F4. ODsay 동적 분배

```python
# 캐시 미스 수 측정
to_fetch_all_1 = [c for c in cells if c not in cached_1]
to_fetch_all_2 = [c for c in cells if c not in cached_2]  # dual만

TOTAL_LIMIT = MAX_FETCH_CELLS_PER_CALL  # 200
half = TOTAL_LIMIT // 2  # 100

if not dual:
    to_fetch_1 = sorted(to_fetch_all_1, key=cell_dist_fn(wp))[:TOTAL_LIMIT]
    to_fetch_2 = []
else:
    n1 = len(to_fetch_all_1)
    n2 = len(to_fetch_all_2)
    if n1 <= half and n2 <= half:
        take_1, take_2 = n1, n2
    elif n1 <= half:
        take_1 = n1
        take_2 = min(n2, TOTAL_LIMIT - n1)
    elif n2 <= half:
        take_2 = n2
        take_1 = min(n1, TOTAL_LIMIT - n2)
    else:
        take_1, take_2 = half, half
    to_fetch_1 = sorted(to_fetch_all_1, key=cell_dist_fn(wp))[:take_1]
    to_fetch_2 = sorted(to_fetch_all_2, key=cell_dist_fn(wp_2))[:take_2]
```

asyncio.gather로 두 wp 동시 호출.

### F5. 카드 쿼리 — self-join (dual 모드)

dual 모드: `transit_routes r1 + r2` self-join, `GREATEST(r1.total_time_min, r2.total_time_min)`으로 정렬.
단일 모드: 기존 쿼리 그대로 (r2 JOIN 없음).

`portable.greatest()` 헬퍼 사용:
```python
def greatest(*cols: str) -> str:
    if USE_PG:
        return f'GREATEST({", ".join(cols)})'
    return f'MAX({", ".join(cols)})'  # SQLite도 MAX(a, b) 가변 인수 지원
```

### F6. `_card_to_dict()` 확장

`_build_transit_summary(steps, bc, sc, total_time_min)` 헬퍼 함수로 추출해 wp1/wp2 양쪽에서 재사용.

dual 모드 추가 필드:
```python
card['total_time_min_1'] = r['total_time_min_1']
card['total_time_min_2'] = r['total_time_min_2']
card['transit_summary_1'] = transit_summary_1
card['transit_summary_2'] = transit_summary_2
card['bus_cnt_1'] = r['bus_cnt_1']
card['subway_cnt_1'] = r['subway_cnt_1']
card['bus_cnt_2'] = r['bus_cnt_2']
card['subway_cnt_2'] = r['subway_cnt_2']
card['total_time_min'] = max(r['total_time_min_1'], r['total_time_min_2'])
```

### F7. `_make_pick_reason()` dual 컨텍스트 (ai.py)

```python
t1 = c.get('total_time_min_1')
t2 = c.get('total_time_min_2')
if t1 is not None and t2 is not None:
    max_t = max(t1, t2)
    if max_t <= 30:
        prefix = '두 직장 모두 30분 이내'
    elif max_t <= 40:
        prefix = '두 직장 모두 40분 이내'
    else:
        prefix = f'두 직장 모두 {max_t}분 이내'
    return f"{prefix} · '{pt}' 슬롯 최소가 ({slot_size}곳 중)"
```

### F8. UI — search.html

`+ 다른 가족 직장 추가 (맞벌이)` 버튼 → W2 입력란 노출. W1 라벨도 함께 표시.

### F9. UI — result.html

- 추천 칩 1 (통근): dual → `W1 25분 · W2 32분`
- 일반 카드 commute-chip: 동일 로직
- 지도: W1 red 핀 (`W1 직장`), W2 blue 핀 (`W2 직장`)
- summary bar: `W1 (강남역) + W2 (마포역) | 가격 | 시간 | 평형`
- 교집합 0건: 친구 톤 안내 메시지 + "조건 다시 입력" CTA

---

## 5. Non-functional Requirements

- **성능**: ODsay 동적 분배로 단일 모드 대비 total 호출 수 유지
- **Vercel 60초**: `WALL_CLOCK_BUDGET_S = 50` 그대로
- **Supabase/pgBouncer**: `GREATEST()` Postgres native 지원. SQLite는 `MAX(a, b)`
- **DB 스키마 변경 없음**: DDL 없음, 마이그레이션 불필요
- **하위 호환**: `workplace_address_2 IS None` → 기존 단일 모드 100% 동일 동작

---

## 6. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| `workplace_address_2` 미입력 | 기존 단일 모드, 회귀 없음 |
| 두 주소 동일 | 422 Validation Error |
| wp_2 Kakao geocode 실패 | 400 `"두 번째 주소 변환 실패: ..."` |
| 두 직장 거리 멀어 교집합 후보 0 | `cards: []` + 친구 톤 안내 |
| wp_1 캐시 hit, wp_2 캐시 miss | wp_2만 ODsay 호출 (동적 분배 → wp_2가 200까지), `partial_wp: 2` |
| `effective_max_min` 적용 | `max(t1, t2) <= effective_max_min` 조건 만족 단지만 카드 |

---

## 7. Acceptance Criteria

- [x] **AC1**: `workplace_address_2` 입력 시 두 wp 모두 ODsay 호출 → `meta.dual_workplace=true`
- [x] **AC2**: `workplace_address_2` 미입력 시 기존 동작 100% 유지 (테스트 360 통과)
- [x] **AC3**: 카드 정렬이 `max(t1, t2)` 오름차순
- [x] **AC4**: `build_recommendations`가 `max(t1, t2)`로 버킷 분류
- [x] **AC5**: 응답에 `total_time_min_1`, `total_time_min_2`, `transit_summary_1`, `transit_summary_2` 포함
- [x] **AC6**: 추천 카드 칩 1에 `W1 25분 · W2 32분` 형태 표시
- [x] **AC7**: 지도에 W1 (red) + W2 (blue) 핀 시각적 구분
- [x] **AC8**: search.html `+ 다른 가족 직장 추가` 버튼 + 두 번째 주소 입력란 동작
- [x] **AC9**: 두 주소 동일 시 422 메시지 표시
- [x] **AC10**: 교집합 0건 시 친구 톤 안내 메시지 노출
- [x] **AC11**: ODsay 동적 분배: wp_1 미스 30, wp_2 미스 180 → take_1=30, take_2=170
- [x] **AC12**: 두 wp 모두 반경 내 단지만 후보 필터 (교집합)
- [x] **AC13**: `_make_pick_reason` dual 모드 → `"두 직장 모두 30분 이내 · '20평대' 슬롯 최소가"` 형태
- [x] **AC14**: 단일 모드 기존 테스트 360개 통과 (회귀 0)
- [x] **AC15**: `GREATEST()` / `MAX(a, b)` 양쪽 환경에서 동작 (portable.USE_PG 분기)

---

## 8. 구현 메모

> **구현 완료**: 2026-05-27
>
> - `app/portable.py`: `greatest(*cols)` 헬퍼 — Postgres `GREATEST()` / SQLite `MAX()` 분기
> - `app/search.py`: `SearchRequest.workplace_address_2` + `_check_workplace_2` validator, Step 1b wp_2 발급, Step 2 교집합 필터, Step 3 asyncio.gather 동적 분배, Step 4 self-join dual 쿼리 (`ORDER BY MAX(r1, r2)`), `_card_to_dict(dual=True)`, 응답에 `workplace_2` + `meta.dual_workplace` 추가
> - `app/ai.py`: `_make_pick_reason()` dual 분기 — `max(t1, t2)` 기준 prefix 생성
> - `web/search.html`: W2 입력 UI (`+ 다른 가족 직장 추가 (맞벌이)` 버튼, 접기/제거 동작, form submit에 `workplace_address_2` 파라미터 추가)
> - `web/result.html`: `dualMode` 변수, `renderSummary` W2 표시, `chip1Text` dual, `commute-chip` dual, `initMap` W2 파란 핀 (`.pin-workplace-2`), `renderCards` 교집합 0건 친구 톤 안내
> - `tests/test_dual_workplace.py`: 신규 20개 테스트 — 유효성 검사 4개, 파이프라인 11개, 교집합 없음 2개, 하위 호환 3개
> - 전체 테스트: 360/360 통과 (기존 340 + 신규 20)

### 변경된 파일

| 파일 | 변경 유형 | 내용 |
|------|---------|------|
| `app/portable.py` | 수정 | `greatest()` 헬퍼 추가 |
| `app/search.py` | 수정 | SearchRequest.workplace_address_2, dual 분기 전체 |
| `app/ai.py` | 수정 | `_make_pick_reason()` dual 컨텍스트 분기 |
| `web/search.html` | 수정 | dual workplace UI |
| `web/result.html` | 수정 | W1/W2 표시, 지도 W2 핀, 교집합 0건 화면 |
| `tests/test_dual_workplace.py` | 신규 | dual 모드 단위/통합 테스트 |
| `docs/specs/13-dual-workplace.md` | 신규 | 이 문서 |
| `docs/specs/SPEC_GUIDE.md` | 수정 | spec-13 추가, 다음 번호 14 |
