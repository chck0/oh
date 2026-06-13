# Spec 29: 초등학교 도보 POI 추가 (apt_walking_poi)

> 상태: Implemented ✅ | 작성일: 2026-06-05 | 브랜치: chck0527/elementary-poi

## 1. Why (왜)

`apt_walking_poi`에는 중·고등학교만 학교 카테고리(`A`/`A01`)로 들어있고 **초등학교가 빠져 있다**
(원본 POI 데이터셋이 초/중/고 중 초등을 미수집. 기존 "초등학교" 2006건은 정류장 등 노이즈로 B02 등에 흩어짐).
NEIS 교육정보 개방 포털로 초등학교를 받아 중·고와 **똑같은 형식**(이름 + distance_m + walking_min,
카테고리 `A`/`A01`)으로 적재해 학세권 정보를 완성한다. 화면·채팅은 이미 `A=학교`로 표시하므로 코드 변경 최소.

## 2. Scope (범위)

- **포함:** 서울·경기·인천 초등학교를 NEIS에서 수집 → 지오코딩 → 각 단지 도보 15분(~1.1km) 내 초등학교를
  `apt_walking_poi`에 INSERT (lclas=`A`, mlsfc=`A01`). 운영 Supabase에 적재.
- **제외(안 함):** 중·고·대 기존 데이터 수정, 유치원/학원, 학교 등급·학생수 등 부가정보,
  초등학교 외 지역(서울/경기/인천 외 — 단지가 없음).

## 3. 설계 (어떻게)

단지 분포: 서울 2936 / 경기 2687 / 인천 882 = 6505개 (전부 좌표 보유). → NEIS도 이 3개 시도만.

새 스크립트 `scripts/fetch_elementary_poi.py` (멱등·재실행 안전):
- **단계 1**: NEIS `schoolInfo` API로 서울/경기/인천 초등학교 목록(이름+도로명주소) 수집.
  키: `cfg.NEIS_API_KEY`. 페이징(pSize=1000). 로컬 캐시(`data/raw/neis_elem.json`)로 재호출 절감.
- **단계 2**: 주소 → 좌표 지오코딩 (Kakao REST, `cfg.KAKAO_REST_API_KEY`). 결과 캐시해 재지오코딩 방지.
- **단계 3**: 각 단지(apartments.lat/lng)에서 haversine 거리 계산 → 도보 15분(1100m) 이내 초등학교만 선별.
  `walking_min = round(distance_m / 75)` (기존 데이터 역산값, 중·고와 동일 공식).
- **단계 4**: `apt_walking_poi`에 INSERT. **멱등성**: 먼저
  `DELETE FROM apt_walking_poi WHERE poi_lclas_cd='A' AND poi_mlsfc_cd='A01' AND poi_nm LIKE '%초등학교%'`
  로 우리가 넣은 행만 제거 후 재삽입 (중·고는 초등학교 패턴 불일치 → 안전).
- **단계 5**: result.html 주석 라벨 `A=학교(중고등)` → `A=학교(초중고)`.

- DB 변경: `apt_walking_poi`에 데이터 INSERT만 (스키마 변경 없음). 운영 Supabase 직접.
- API 변경: 없음 (화면·채팅이 이미 `A`=학교로 렌더).
- 엣지케이스: 지오코딩 실패 학교는 스킵(로그). 거리 0~1100m만. 중복 단지-학교쌍 방지.
- 되돌리기: 위 DELETE 한 줄로 전량 제거 가능.

> **구현 중 변경**: mlsfc는 `A01`이 아니라 **전용 코드 `A04`** 사용. 조사 결과 기존 A 서브코드는
> A01=중학교 / A02=고등학교 / A03=대학으로 이미 점유돼 있었고, 초등을 A01에 넣으면 "○○초(신설예정)"처럼
> '초등학교' 글자 없는 학교를 이름 기반 멱등 DELETE가 못 잡는 문제가 있었다. 전용 `A04`로 분리해
> 이름 무관 정확 멱등을 달성. 화면은 lclas='A'(="학교")로 묶으므로 표시는 중·고와 동일.

## 4. 완료 조건 (Acceptance Criteria)

- [x] AC1: `scripts/fetch_elementary_poi.py` 생성, `cfg.NEIS_API_KEY`/`cfg.KAKAO_REST_API_KEY` 사용 (하드코딩 0)
- [x] AC2: 멱등 — 2회 실행해도 A04 30,430건 동일 (중복 INSERT 없음)
- [x] AC3: 운영 Supabase에 초등학교(A/A04) **30,430건** 적재됨 (단지 6,118개)
- [x] AC4: 중·고와 동일 형식 (poi_nm + distance_m + walking_min, lclas=A) — mlsfc만 A04로 분리
- [x] AC5: 모든 초등 POI distance_m ≤ 1100 (위반 0건)
- [x] AC6: 샘플 단지 A11014001 detail에 초등학교 3개가 category='A'로 노출 확인
- [x] AC7: result.html 라벨 'A=학교(초중고)' 갱신, pytest 388 통과 (회귀 없음)

### 결과
- NEIS 2,272개 수집 → 지오코딩 2,264개 성공(8 실패 스킵) → `data/raw/neis_elem.json` 캐시
- 6,505개 단지 × 도보15분(1100m) → 30,430 POI (A/A04)
- 중·고·대(A01/A02/A03) 무변경. 멱등·되돌리기(DELETE A04) 가능.
