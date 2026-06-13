# Spec: 경사도 · 재건축/구조 지표 노출 (Slope & Rebuild Indicators)

> **상태**: Implemented
> **작성일**: 2026-06-13
> **구현 브랜치**: claude/happy-curie-e7ry0s

---

## 1. Why (왜 만드는가)

- MANIFESTO 연결:
  - "데이터가 없으면 말하지 않는다" → 이미 공식 데이터(`apt_slope`, `building_register`)가
    DB에 수집되어 있는데 화면에서 안 쓰고 있다. **있는 사실을 정직하게 보여주자.**
  - "비교가 판단을 만든다" → 통근시간·가격 외에 입지(경사)·재건축 잠재력이라는
    새로운 비교 축을 더한다.
- 실구매자(30대 첫 집)가 임장 전에 꼭 알고 싶은데 지금 답이 없는 질문:
  - "도보 N분이라는데 그 길이 **언덕이야 평지야**?" (겨울 빙판·장보기·체감거리)
  - "이 구축, **나중에 재건축 기대할 수 있어**?" → 용적률·건폐율·구조·사용승인일이 유일한 공식 근거
- Why Tree 계층: **신뢰할 수 있는 데이터** (공식 데이터를 더 투명하게) +
  **이해하기 쉬운 설명** (도(°) 숫자를 "평지/완경사" 같은 친구 언어로 번역).

---

## 2. User Story

```
As a 직장 근처 첫 집을 알아보는 30대 1인 가구,
I want to 단지 상세에서 그 단지가 언덕인지 평지인지, 그리고 용적률·건폐율·구조·사용승인일을 보고 싶다,
so that 임장 가기 전에 도보 통근의 현실성과 재건축 잠재력을 가늠할 수 있다.
```

---

## 3. Scope

### In-scope
- `GET /api/apt/{apt_seq}/detail` 응답의 `building` 객체에 필드 추가:
  - 경사도: `apt_slope`(단지 평균 경사) + 등급 라벨
  - 재건축/구조: 용적률(`vlRat`), 건폐율(`bcRat`), 구조(`strctCdNm`), 사용승인일(`useAprDay`)
- 상세 모달 **단지정보 탭**에 "입지·구조" 섹션 신설 — 위 값 표시
- 데이터 없는 단지는 해당 행 **숨김**(빈 값 "-" 남발 금지)
- 데모 시드(`seed_demo_data.py`)에 `apt_slope`·`building_register` 행 추가 →
  로컬 데모에서도 검증 가능

### Out-of-scope (Non-goals)
- 카드(목록)에 경사 칩 노출 → v2 후보 (상세에서 먼저 검증)
- "재건축 유망/불리" 같은 **단정적 판단** → 매니페스토 위반. 사실(숫자)만 표시하고
  해석은 친구 채팅이 담당
- **주변 경사(`ngbr_slope_avg`)** → 단지 경사만 단순하게 (Q3 확정)
- 경사 도(°) 원본값을 본문에 직접 노출 → 체감 라벨로 번역, 원본은 툴팁으로만 (Q1 확정)
- 경사도 데이터 신규 수집/갱신 파이프라인 → 이미 수집된 데이터 노출만 (수집은 별도 spec)
- 지도 위 경사 시각화(등고선 등)

---

## 4. Functional Requirements

- F1. detail 쿼리에 `LEFT JOIN apt_slope s ON a.kaptCode = s.kaptCode` 추가,
  `apt_slope_avg`를 가져온다. (주변 경사는 사용 안 함)
- F2. detail 쿼리에 `building_register` 집계 서브쿼리를 `LEFT JOIN` 한다 (단지당 동 여러 행):
  - 용적률 `vlRat`, 건폐율 `bcRat`: `AVG` (단지 대표값)
  - 구조 `strctCdNm`: 최빈값(가장 많은 동의 구조)
  - 사용승인일 `useAprDay`: `MIN`(가장 이른 날 = 단지 최초 준공)
- F3. **경사도 — 체감 라벨 + 한 줄 설명 (Q1 확정).** 단지 평균 경사를 4단계로 번역.
  본문엔 라벨+체감설명만, 도(°) 원본은 툴팁(`title` 속성)으로만 노출.
  | 평균 경사 | 라벨 (`slope_label`) | 한 줄 체감 (`slope_hint`) |
  |---|---|---|
  | < 3° | 평지 | 걷기 편해요 |
  | 3 ~ 7° | 완만한 오르막 | 살짝 오르막이에요 |
  | 7 ~ 12° | 언덕 | 오르막이 확실히 느껴져요 |
  | ≥ 12° | 가파른 언덕 | 짐 들고 오르긴 부담돼요 |
  - 표시 형식(예): `평지 · 걷기 편해요` + CSS 경사 인디케이터 막대(4단계). 도(°)는 hover 툴팁.
- F4. **용적률/건폐율 — 가벼운 중립 힌트 (Q2 확정).** 숫자 + "전형적 범위 대비 위치"
  한 단어만 덧붙인다. 단정 판단 단어 금지.
  - 용적률(`far`): 대개 아파트 200~250% 기준 → `< 180%` 낮은 편 / `180~280%` 보통 / `> 280%` 높은 편
    표시 예: `210% · 보통` (+ 툴팁/캡션 "아파트 대개 200~250%")
  - 건폐율(`bcr`): 대개 15~25% 기준 → `< 15%` 낮은 편(동 간격 여유) / `15~25%` 보통 / `> 25%` 높은 편(밀집)
    표시 예: `18% · 낮은 편 (동 간격 여유)`
  - 힌트 라벨은 일반 도메인 상식(밴드 비교)일 뿐, 특정 단지의 재건축 가부는 판단하지 않음.
- F5. 사용승인일(`YYYYMMDD`)은 `YYYY.MM` 형식으로 가공해 표시.
- F6. 모든 신규 값은 **null이면 행 자체를 렌더링하지 않는다** (정직한 빈값 처리).
- F7. `building` 객체에 신규 키 추가:
  `slope_avg`(툴팁용 원본), `slope_label`, `slope_hint`,
  `far`, `far_level`, `bcr`, `bcr_level`, `structure`, `approve_ym`.
  (level/label/hint 등 라벨 변환은 백엔드에서 수행 — 프론트는 표시만)

---

## 5. Non-functional Requirements

- **성능**: detail 단일 쿼리에 JOIN 2개 추가 — 인덱스(`kaptCode` PK) 존재, 영향 미미.
  building_register 집계는 서브쿼리 1회.
- **신뢰성**: 신규 테이블 조회 실패 시 `except` + `conn.rollback()` 후 해당 필드만
  None 처리 (기존 상세 화면은 정상 동작). spec-trap "trade_tags 미존재 500" 패턴 준수.
- **호환성**: SQLite(로컬/데모) + Postgres(Supabase) 양쪽. 집계 함수(AVG/MIN)는
  양쪽 호환, 최빈값은 `app/portable.py`에 헬퍼 추가 또는 Python 레벨 처리.
- **모바일**: 단지정보 탭 detail-kv 그리드 재사용 → 반응형 자동.

---

## 6. UX / Vibe

- 경사: 도(°) 숫자를 본문에서 **빼고**, 걷는 사람 체감 언어("평지 · 걷기 편해요")로 번역.
  1인 가구 일상(캐리어·장보기·겨울 출퇴근) 정서를 한 줄 체감 설명에 담는다.
  원본 도(°)는 궁금한 사람만 보도록 툴팁으로.
- 시각: 디자인 시스템 규칙 준수 — 이모지 금지, 막대/인디케이터는 CSS로.
  경사 4단계 인디케이터(살짝 기운 막대)로 직관 보강.
- 용적률/건폐율: 숫자 + `낮은 편/보통/높은 편` 한 단어. 특정 단지 재건축 가부 단정 금지.
- 섹션 제목: "입지·구조" — 단지정보 탭 안, 기존 "단지 정보" 아래.
- 에러 톤: 데이터 없으면 조용히 숨김 (오류 메시지 X).

---

## 7. Data Model

신규 테이블 없음. 기존 테이블 조회만:

```
apt_slope            (kaptCode PK)
└── apt_slope_avg: float  -- 단지 평균 경사(도). 사용. (ngbr_* 는 미사용)

building_register    (kaptCode, mgmBldrgstPk PK) — 단지당 동 여러 행
├── vlRat: float        -- 용적률(%)      → AVG
├── bcRat: float        -- 건폐율(%)      → AVG
├── strctCdNm: text     -- 구조명          → 최빈값
└── useAprDay: text     -- 사용승인일 YYYYMMDD → MIN
```

영향받는 테이블: `apt_slope`, `building_register` (읽기 전용)

---

## 8. API / Interface

```python
GET /api/apt/{apt_seq}/detail?wp_id={wp_id}

Response (building 객체에 추가):
  "building": {
     ... 기존 필드 ...,
     "slope_avg":   2.1,             # float | null  (툴팁용 원본 도°)
     "slope_label": "평지",           # str | null
     "slope_hint":  "걷기 편해요",      # str | null
     "far":         210.5,           # 용적률 % | null
     "far_level":   "보통",           # 낮은 편 | 보통 | 높은 편 | null
     "bcr":         18.0,            # 건폐율 % | null
     "bcr_level":   "낮은 편",         # 낮은 편 | 보통 | 높은 편 | null
     "structure":   "철근콘크리트구조",  # str | null
     "approve_ym":  "2004.03"        # str | null
  }
```

프론트: `_renderDetail()` 단지정보 탭에 "입지·구조" 섹션 추가.

---

## 9. Edge Cases

| 케이스 | 기대 동작 |
|---|---|
| apt_slope 행 없음 | 경사 행 숨김 |
| building_register 행 없음 | 용적률/건폐율/구조/승인일 행 숨김 |
| 테이블 자체 미존재(구버전 DB) | try/except + rollback, 나머지 상세 정상 |
| useAprDay 형식 비정상 | 가공 실패 시 None → 행 숨김 |
| 경사값 음수/이상치 | 라벨 변환은 양수 기준(음수는 0 취급=평지); 비정상은 숨김 |
| 일부 동만 데이터 존재 | AVG/MIN/최빈값이 존재 행 기준으로 계산 |
| 용적률/건폐율 0 또는 이상치 | level 라벨 생략, 숫자만 표시 (또는 행 숨김) |

---

## 10. Acceptance Criteria

- [x] AC1: 데모 단지(예: DEMO001) 상세에 "입지·구조" 섹션이 뜨고
      경사 라벨·체감설명·용적률·건폐율·구조·사용승인일이 표시된다
- [x] AC2: 해당 데이터가 없는 단지는 행이 숨겨지고 "-"가 남발되지 않는다
- [x] AC3: 경사가 **체감 라벨+한 줄 설명**으로 표시되고(예: "평지 · 걷기 편해요"),
      도(°) 원본은 본문에 없으며 툴팁으로만 확인된다 + CSS 인디케이터 막대 노출
- [x] AC4: 용적률/건폐율에 `낮은 편/보통/높은 편` 힌트가 붙되 재건축 가부 단정 단어는 없다
- [x] AC5: 신규 테이블 조회가 실패해도 상세 화면 나머지는 정상 (500 없음)
- [x] AC6: 단정적 판단 단어 없이 사실 수치/일반 밴드만 노출 (매니페스토 준수)
- [x] 로컬(SQLite/데모) 동작 확인 (Vercel/Supabase는 동일 쿼리·동일 어댑터로 호환)
- [x] 신규/회귀 테스트 통과 (detail 엔드포인트 단위 테스트 13건 추가, 총 392 passed)

---

## 11. Open Questions

- Q1: 경사 표현 → **체감 라벨 + 한 줄 설명 + CSS 인디케이터, 도(°)는 툴팁.** ✅ 확정
- Q2: 용적률/건폐율 힌트 → **`낮은 편/보통/높은 편` + 일반 기준 밴드.** ✅ 확정
- Q3: 주변 경사 → **미사용(단지 경사만).** ✅ 확정
- Q4(남음): `apt_slope_avg`의 **단위가 도(°)인지 % 구배인지** 실 Supabase 데이터로 확인 필요.
  임계값(F3)은 도(°) 가정. 단위가 다르면 임계값 상수만 조정 (로직 변경 없음).
  → 로컬 데모는 도(°) 가정값으로 시드해 화면 검증, 단위 확정은 프로덕션 데이터로 추후 보정.

---

## 12. 구현 메모 (Implement 후 채우기)

- 변경된 파일:
  - `app/detail.py`: 라벨 변환 순수함수(`_slope_label`/`_far_level`/`_bcr_level`/`_approve_ym`) +
    apt_detail에 `_q_infra` 병렬 쿼리 추가(apt_slope·building_register 조회·집계).
    (main 병합 시 search.py 분할로 detail 엔드포인트가 `app/detail.py`로 이동 → 이식)
  - `web/result.html`: 단지정보 탭 "입지·구조" 섹션 + 경사 CSS 인디케이터(`.slope-ind`)
  - `scripts/seed_demo_data.py`: apt_slope·building_register 스키마/시드 (INFRA dict)
  - `tests/test_detail_endpoint.py`: 라벨 변환 단위 + 통합 + graceful 테스트 13건
- 주요 결정 사항:
  - **JOIN 대신 kaptCode 별도 조회 + try/except**: 두 테이블을 각각 guarded query로 분리해
    한쪽 미존재/실패가 상세 전체를 깨지 않도록(trade_tags 함정 패턴). 실패 시 `conn.rollback()`.
  - **집계는 Python 레벨**: building_register 동별 행 → AVG(용적률/건폐율)·`Counter` 최빈값(구조)·
    MIN(사용승인일). SQL `mode()` 방언 차이 회피 → SQLite/Postgres 동일 동작.
  - **라벨 변환은 백엔드**: 프론트는 표시만. 경사 도(°)는 `title` 툴팁으로만 노출.
  - **경사 레벨(1~4)은 백엔드 산출**(`slope_level`): 프론트 인디케이터 칸 수가 라벨
    문자열에 결합되지 않도록 정수로 내려줌 (코드 리뷰 반영).
  - **kaptCode 재사용**: 상세 메인 쿼리에 `a.kaptCode` 추가해 별도 조회 제거 (리뷰 반영).
- 알려진 제약:
  - `apt_slope_avg` 단위(도°/% 구배) 미확정 → 임계값은 도(°) 가정. 프로덕션 데이터로
    확인 후 임계값 상수만 보정하면 됨(로직 불변). Open Q4 참고.
  - 카드(목록) 경사 칩은 v2로 보류 — 현재는 상세 모달에서만 노출.
