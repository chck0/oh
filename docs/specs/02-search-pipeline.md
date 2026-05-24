# Spec: 검색 파이프라인 (POST /api/search)

> **상태**: Implemented  
> **구현 파일**: `app/search.py`, `app/workplaces.py`, `app/transit.py`, `app/db.py`  
> **작성일**: 2026-05-24 (retrospective)

---

## 1. Why

MANIFESTO — "데이터가 없으면 말하지 않는다."  
직장 주소 → 공공 대중교통 데이터 → 실거래가 → 추천 카드 순서로 신뢰할 수 있는 데이터만 사용.  
Vercel 60초 제약 안에서 최대한 많은 셀을 처리하고, 초과분은 다음 검색에서 자연히 채운다.

---

## 2. User Story

```
As a API 소비자 (result.html),
I want to 직장 주소와 조건을 POST하면,
so that 조건에 맞는 아파트 카드 목록과 통계·추천 결과를 받는다.
```

---

## 3. Scope

### In-scope
- Kakao REST API로 직장 주소 → 좌표 변환 + wp_id 발급
- 반경 내 아파트 필터링 (is_apt=1, recent_trade=3)
- ODsay 멀티키 병렬 대중교통 경로 호출 + DB 캐싱
- 실거래가(trade_recent) 쿼리 + 카드 조합
- 추천 로직 호출 (ai.py)
- LLM 코멘트 백그라운드 생성 + 캐시 조회

### Out-of-scope
- 전세·월세 조건
- 호가 데이터
- 5~10년 가격 예측

---

## 4. Functional Requirements

- F1. `workplace_address` → Kakao REST geocode → `(lat, lng)` + `wp_id` 발급 (workplaces 테이블 upsert)
- F2. 통근시간 여유분 15분 차감: `effective_max_min = max_minutes - 15`
- F3. 반경 계산: `radius_km = effective_max_min × 20 / 60`
- F4. 반경 내 `is_apt=1 AND recent_trade=3` 단지 목록 필터
- F5. 해당 단지의 grid_key 셀 중 캐시 미스만 ODsay 호출
  - `passed_filter=0` 캐시(실패 이력) 삭제 후 재호출
  - 거리 오름차순 상위 250셀만 처리 (Vercel 60s 제약)
  - 초과분은 `partial=true` 메타로 클라이언트에 알림
- F6. ODsay 호출: 4키 × 4 동시 병렬 (최대 16 동시)
- F7. 카드 쿼리: `apartments JOIN transit_routes JOIN trade_recent` 단일 쿼리
  - `rank=1` 경로 (최적 경로 1개만)
  - `pyeong_type IN (?)` 사용자 선택 평형만
  - `deal_amount_int <= max_price`
- F8. 카드별 최근 거래 4건: ROW_NUMBER() OVER (PARTITION BY apt_seq, pyeong_type) CTE
- F9. 추천 로직 호출 → `is_recommended`, `bucket_label`, `pick_reason` 부여
- F10. LLM 코멘트: 캐시 우선 → 미스 카드는 BackgroundTasks로 비동기 생성
- F11. 응답: `cards`, `stats`, `buckets`, `meta`, `wp_id`, `llm_pending`

---

## 5. Non-functional Requirements

- **성능**: Vercel Hobby 60초 이내 응답
- **신뢰성**: ODsay 키 실패 시 다음 키로 자동 폴백
- **DB 호환**: SQLite(로컬) ↔ Postgres/pgBouncer(Vercel) 자동 전환
- **보안**: SearchRequest Pydantic 검증 (workplace_address 2~200자, max_minutes 10~60, pyeong_types 허용값)

---

## 6. UX / Vibe

API이므로 UX 없음. result.html이 소비자.  
`partial=true` 시 result.html이 amber 배너로 사용자에게 안내.

---

## 7. Data Model

**입력 (SearchRequest)**

| 필드 | 타입 | 범위 | 기본값 |
|---|---|---|---|
| workplace_address | str | 2~200자 | 필수 |
| max_minutes | int | 10~60 | 60 |
| max_price | int (만원) | 1,000~2,000,000 | 50,000 |
| pyeong_types | list[str] | 허용 6종, 1~6개 | ['10평대','20평대'] |
| min_kaptdaCnt | int\|None | 0~100,000 | None(=100) |

**출력 (응답 JSON)**

```json
{
  "wp_id": 42,
  "llm_pending": true,
  "workplace": { "address_input": "...", "address_norm": "...", "lat": 0.0, "lng": 0.0 },
  "stats": { "total": 48, "avg_price": 45000, "commute_curve": [...], "pyeong_breakdown": [...], "age_breakdown": {...} },
  "buckets": [ {"idx": 0, "min": 0, "max": 30, "label": "30분 이내"}, ... ],
  "cards": [ { "apt_seq": "...", "apt_nm": "...", "is_recommended": true, ... } ],
  "meta": { "partial": false, "odsay_calls_made": 12, "odsay_passed": 10, ... }
}
```

**관련 테이블**: `workplaces`, `apartments`, `transit_cache`, `transit_routes`, `trade_recent`, `kapt_complexes`, `apt_pt_friend_comment`

---

## 8. API / Interface

```
POST /api/search
Content-Type: application/json

Request Body: SearchRequest (JSON)
Response: 200 OK (JSON) | 400 주소 변환 실패 | 422 검증 실패 | 500 서버 오류
```

폴링 엔드포인트:

```
GET /api/apt/{apt_seq}/comment?wp_id={wp_id}&pyeong_type={pt}
→ LLM 코멘트 완료 여부 + comment 반환
```

---

## 9. Edge Cases

| 케이스 | 현재 동작 |
|---|---|
| 반경 내 단지 없음 | `cards: []`, stats 최소값 응답 |
| 조건에 맞는 거래 없음 | `cards: []` |
| ODsay 250셀 초과 | `meta.partial=true`, 초과분 다음 검색에서 채움 |
| ODsay 키 전체 실패 | 경로 없는 단지 제외 (transit_routes 미등록) |
| LLM API 실패 | `llm_pending=true` 유지, 코멘트 빈 문자열 |
| pgBouncer Transaction mode | `prepare_threshold=None` 자동 설정 |

---

## 10. Acceptance Criteria

- [x] 직장 주소 Kakao geocode 성공 시 wp_id 반환
- [x] 반경 계산 후 nearby 단지만 필터
- [x] ODsay 캐시 히트 시 재호출 없음
- [x] 250셀 초과 시 partial=true
- [x] 카드에 is_recommended, bucket_label, pick_reason 포함
- [x] llm_pending=true 시 클라이언트가 폴링 시작

---

## 11. 개선 아이디어 (Open)

- BackgroundTasks → Supabase Edge Function으로 이전 (Vercel 서버리스 함수 종료 후 BG 태스크 죽는 문제)
- 셀 프리워밍 스케줄러 (신규 직장 등록 후 비동기 사전 캐싱)
- ODsay 대안 fallback (카카오 대중교통 API)
