# Spec: 경사도 · 재건축/구조 지표 노출 (Slope & Rebuild Indicators)

> **상태**: Draft
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
- 경사도 데이터 신규 수집/갱신 파이프라인 → 이미 수집된 데이터 노출만 (수집은 별도 spec)
- 지도 위 경사 시각화(등고선 등)

---

## 4. Functional Requirements

- F1. detail 쿼리에 `LEFT JOIN apt_slope s ON a.kaptCode = s.kaptCode` 추가,
  `apt_slope_avg`를 가져온다.
- F2. detail 쿼리에 `building_register` 집계 서브쿼리를 `LEFT JOIN` 한다 (단지당 동 여러 행):
  - 용적률 `vlRat`, 건폐율 `bcRat`: `AVG` (단지 대표값)
  - 구조 `strctCdNm`: 최빈값(가장 많은 동의 구조)
  - 사용승인일 `useAprDay`: `MIN`(가장 이른 날 = 단지 최초 준공)
- F3. 경사도 등급 라벨 변환 (단지 평균 경사 기준, 잠정 임계값):
  | 평균 경사 | 라벨 |
  |---|---|
  | < 3° | 평지 |
  | 3 ~ 7° | 완만한 경사 |
  | 7 ~ 12° | 경사 있음 |
  | ≥ 12° | 급경사 |
  - 표시 형식: `평지 (2.1°)` — 라벨 + 원본값 괄호
- F4. 사용승인일(`YYYYMMDD`)은 `YYYY.MM` 형식으로 가공해 표시.
- F5. 모든 신규 값은 **null이면 행 자체를 렌더링하지 않는다** (정직한 빈값 처리).
- F6. `building` 객체에 신규 키 추가:
  `slope_avg`, `slope_label`, `far`(용적률), `bcr`(건폐율), `structure`, `approve_ym`.

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

- 도(°) 같은 전문 숫자를 그대로 던지지 않고 **"평지/완만한 경사"로 번역** 후 괄호에 원본.
- 용적률/건폐율은 사실 그대로. 판단 단어("재건축 유망") 금지.
- 섹션 제목: "입지·구조" — 단지정보 탭 안, 기존 "단지 정보" 아래.
- 에러 톤: 데이터 없으면 조용히 숨김 (오류 메시지 X).

---

## 7. Data Model

신규 테이블 없음. 기존 테이블 조회만:

```
apt_slope            (kaptCode PK)
└── apt_slope_avg: float  -- 단지 평균 경사(도). 사용.

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
     "slope_avg":  2.1,            # float | null
     "slope_label": "평지",         # str | null
     "far":         210.5,         # 용적률 % | null
     "bcr":         19.8,          # 건폐율 % | null
     "structure":   "철근콘크리트구조", # str | null
     "approve_ym":  "2004.03"      # str | null
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
| 경사값 음수/이상치 | 라벨 변환은 양수 기준; 비정상은 원본만 또는 숨김 |
| 일부 동만 데이터 존재 | AVG/MIN/최빈값이 존재 행 기준으로 계산 |

---

## 10. Acceptance Criteria

- [ ] AC1: 데모 단지(예: DEMO001) 상세에 "입지·구조" 섹션이 뜨고
      경사 라벨·용적률·건폐율·구조·사용승인일이 표시된다
- [ ] AC2: 해당 데이터가 없는 단지는 행이 숨겨지고 "-"가 남발되지 않는다
- [ ] AC3: 경사 도(°) 값이 등급 라벨로 변환되어 표시된다 (예: "평지 (2.1°)")
- [ ] AC4: 신규 테이블 조회가 실패해도 상세 화면 나머지는 정상 (500 없음)
- [ ] AC5: 단정적 판단 단어 없이 사실 수치만 노출 (매니페스토 준수)
- [ ] 로컬(SQLite/데모) + Vercel(Supabase) 양쪽 동작
- [ ] 신규/회귀 테스트 통과 (detail 엔드포인트 단위 테스트 확장)

---

## 11. Open Questions

- Q1: `apt_slope_avg`의 **단위가 도(°)인지 퍼센트 구배(%)인지** 실데이터로 확인 필요.
  → 임계값(F3)은 도(°) 가정. 단위가 다르면 임계값만 조정.
- Q2: 용적률/건폐율에 아주 가벼운 중립 힌트(예: 평균 대비 위치)를 붙일까,
  아니면 숫자만 둘까? → v1은 숫자만(안전), 힌트는 v2 검토.
- Q3: 주변 경사(`ngbr_slope_avg`)도 같이 보여줄까? → v1 단지 경사만, 단순하게.

---

## 12. 구현 메모 (Implement 후 채우기)

- 변경된 파일: (구현 시 작성)
- 주요 결정 사항:
- 알려진 제약:
