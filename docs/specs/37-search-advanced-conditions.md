# Spec 37: 검색 상세조건 펼침 (평형·준공연도·세대수)

> 상태: Implemented | 작성일: 2026-06-14 | 브랜치: hjkang83
> 결정(2026-06-14): 평형 기본=전체선택, 섹션은 번호 없는 "상세조건 (선택)".

## 1. Why (왜)

- **문제:** 현재 검색 화면은 주소·가격·통근시간만 받고, 평형은 내부적으로 6종 전체를 강제로 보낸다(`search.html` 제출 시 `pyeong_types` 하드코딩). 준공연도·세대수는 아예 안 보낸다. 그래서 "20평대만", "2015년 이후만", "500세대 이상만" 같은 조건으로 좁혀서 분석할 수 없다.
- **사용자가 얻는 것:** 기본 화면은 그대로 단순하게 두되, **"상세조건"을 펼치면** 원하는 평형·준공연도·세대수를 골라 그 조건으로 분석받는다.
- **이미 갖춰진 것:** 백엔드 `SearchRequest`는 `pyeong_types`·`build_year_min`·`min_kaptdaCnt`를 이미 지원하고, `result.html`도 이 값들을 URL 파라미터에서 읽어 `/api/search`에 전달한다. **빠진 고리는 search.html이 이 조건을 수집·전송하지 않는 것뿐.** (게다가 search.html prefill 코드엔 `name="pyeong"/"mincnt"/"build_year_min"` 복원 로직이 이미 남아 있음 → 입력만 추가하면 "조건 다시 입력" 복원도 자동.)

## 2. Scope (범위)

- **포함:**
  - search.html 통근시간 섹션 아래에 **접이식 "상세조건" 섹션**(기본 접힘). 현재 입력 화면(주소·가격·통근)은 그대로 유지.
  - 평형: 체크박스 6종(10평미만/10평대/20평대/30평대/40평대/50평대+), **기본 전체 선택**(= 현재 동작 유지)
  - 준공연도(`build_year_min`): 라디오 — 제한없음/2000·2010·2015·2020년 이후
  - 세대수(`min_kaptdaCnt`): 라디오 — 제한없음/300·500·1000·1500세대 이상
  - 제출 시 **선택값을 result.html URL 파라미터로 직렬화** (평형은 실제 선택분, 준공/세대수는 선택 시에만)
  - "조건 다시 입력" 시 복원(기존 prefill 활용)
- **제외(안 함):**
  - 백엔드/`/api/search` 변경 (이미 지원) · result.html reqBody 변경 (이미 읽음)
  - 가격 하한(min_price)은 이미 가격 섹션에 있으므로 상세조건에 중복 추가 안 함
  - 결과 화면의 별도 필터 패널 (이번 범위 아님)

## 3. 설계 (어떻게)

- **건드리는 파일:** `web/search.html` 만 (상세조건 HTML + CSS + 제출 직렬화). 백엔드·result.html 무관.
- **DB 변경:** 없음 · **API 변경:** 없음

- **HTML:** 통근시간 섹션 뒤에 접이식 섹션(번호 없는 보조 또는 "4 상세조건 (선택)"). 펼침 토글 + body(평형 체크박스 그리드, 준공연도 라디오, 세대수 라디오). 입력 `name`은 prefill 규약과 일치: `name="pyeong"`(value=평형명), `name="build_year_min"`(value=연도/빈값), `name="mincnt"`(value=세대수/빈값).

- **제출 직렬화(submit 핸들러):**
  ```
  pyeong = checked된 input[name=pyeong] 값들. 0개면 전체(6종)로 폴백.
  params.set('pyeong_types', pyeong.join(','))   // 기존 하드코딩 제거
  build = input[name=build_year_min]:checked.value; if(build) params.set('build_year_min', build)
  mincnt = input[name=mincnt]:checked.value;       if(mincnt) params.set('min_kaptdaCnt', mincnt)
  ```

- **prefill:** 기존 코드(`input[name=pyeong]`/`[name=mincnt]`/`[name=build_year_min]`)가 이미 복원. 평형 param 없으면 전체 체크 유지.

- **엣지케이스:**
  | 케이스 | 동작 |
  |---|---|
  | 상세조건 안 펼침 | 기본값(평형 전체·준공/세대수 제한없음) = 현재와 동일 결과 |
  | 평형 0개 선택 | 전체 6종으로 폴백(빈 결과 방지) |
  | 준공/세대수 "제한없음" | 해당 param 미전송 |
  | 조건 다시 입력 | 평형·준공·세대수 복원 |
  | 모바일 | 기존 칩/체크박스 스타일 재사용, 접이식이라 공간 최소 |

## 4. 완료 조건 (Acceptance Criteria)

- [x] AC1: 통근시간 아래 "상세조건 (선택)" 접이식 섹션, 기본 접힘 (주소·가격·통근 화면 그대로)
- [x] AC2: 평형 체크박스(기본 전체 6종), 준공연도·세대수 라디오 선택 가능 (기존 .check-chip 스타일 재사용)
- [x] AC3: 분석하기 → 선택값이 result URL(`pyeong_types`/`build_year_min`/`min_kaptdaCnt`)에 반영 (라이브: 20·30평대/2015/500 확인)
- [x] AC4: 상세조건 미사용 시 평형 전체·준공/세대수 미전송 = 현재 동작 동일 (기본 로드 검증)
- [x] AC5: "조건 다시 입력" 시 선택값 복원 + 비기본값이면 섹션 자동 펼침 (라이브 확인)
- [x] AC6: 평형 0개 선택 시 전체 6종 폴백
- [x] 순수 프론트(search.html) — 백엔드/result 변경 없음, 데스크톱 검증(스크린샷)

## 5. Open Questions

- Q1: 평형 기본값 = **전체 선택**(현재 동작 유지) 제안. (대안: 20·30평대만 기본) → 전체 권장.
- Q2: 섹션 표기 — "4 상세조건 (선택)" 번호 부여 vs 번호 없는 보조 섹션. → 선택사항이니 번호 없이 "상세조건 (선택)" 제안.
