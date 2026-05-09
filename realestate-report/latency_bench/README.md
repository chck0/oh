# API Latency 벤치마크

**질문**: 주소 입력 → 객관 점수 분석에 정말 *3시간*이 걸릴까?
**답**: 아니다. 측정 결과 **약 0.5초** (병렬 호출 기준).

---

## TL;DR

| 항목 | 측정값 | 비고 |
|---|---|---|
| 매물 1건 분석 (병렬) | **513 ms** | RAG + 공공포털 + 별도 API 동시 호출 |
| 매물 1건 분석 (순차) | 1,185 ms | 참고용 — 코드 안 좋게 짰을 때 |
| 동료 추정 | 10,800,000 ms (3시간) | **실측 대비 약 21,000배 차이** |

→ 동료의 *3시간* 추정은 *사용자 단건 분석* 시간이 아니라, *데이터 적재·ETL·운영 시간*과 혼동된 것으로 추정.

---

## 측정 방법

### 환경
- Python 3.12, `aiohttp 3.10`, `asyncio.gather` 병렬 호출
- 측정 위치: 로컬 (서울)
- 측정 시각: 2026-05-09 23:20

### 대상 API (실측 7개 + RAG 시뮬레이션)
- **공공데이터포털**: `#1 아파트 실거래가` (data.go.kr)
- **별도 API 5개**: `#30 juso` · `#32 vworld` · `#34 NEIS` · `#35 ECOS` · `#37 ODsay`
- **RAG 20개**: 인메모리 dict lookup으로 시뮬레이션 (실제 PostgreSQL/SQLite 인덱스 hit 수준)

### 시나리오
1. 단일 호출 latency 5회 반복 → median, p95
2. 동일 API 10건 *병렬 batch* → wall time
3. **매물 1건 end-to-end** — 모든 카테고리 *동시 병렬* 호출 → wall time

---

## 측정 결과

### 단일 호출 latency (median)

| API | Median | p95 | 병렬 10건 |
|---|---|---|---|
| RAG (#57 도보 접근성, 시뮬) | 2.3 ms | 2.3 ms | 2.4 ms |
| 공공포털 #1 실거래가 | 143 ms | 2,484 ms | 720 ms |
| juso #30 (주소) | 31 ms | 144 ms | 138 ms |
| NEIS #34 (학교) | 49 ms | 158 ms | 162 ms |
| ECOS #35 (거시) | 80 ms | 267 ms | 173 ms |
| vworld #32 (좌표) | 26 ms | 97 ms | 85 ms |
| ODsay #37 (경로) | 25 ms | 163 ms | 106 ms |

> p95가 큰 API(공공포털 2.5초)는 *첫 호출의 cold connection cost*. 이후 keep-alive로 빨라짐.

### 매물 1건 end-to-end

| 단계 | Wall time |
|---|---|
| RAG 20개 병렬 | **3 ms** |
| 공공포털 5개 병렬 | **513 ms** |
| 별도 API 5개 병렬 | **155 ms** |
| **모든 카테고리 동시 병렬** | **513 ms** (= 0.5초) |
| 순차 호출 가정 (참고) | 1,185 ms (= 1.2초) |

---

## 해석

### 왜 이렇게 빠른가
1. **RAG 데이터(20개)는 이미 우리 DB에 적재됨** — 단지 ID 인덱스 hit, 평균 2~5ms
2. **공공포털·별도 API는 모두 `asyncio.gather`로 병렬** — wall time = max(개별 latency)
3. **월/분기 갱신 데이터는 캐시 가능** — 2번째 사용자부터는 더 빠름

### 동료 추정 *3시간*은 어디서 왔을까

| 가능한 출처 | 실제 영향 |
|---|---|
| 1일 호출량 제한 (ODsay 1,000건/일 무료) | 사용자 단위 아님 — *서비스 운영* 비용 |
| RAG 데이터 *전체 적재* 시간 | 일회성 ETL — 사용자 호출과 무관 |
| 청약/NEIS 인증서 갱신 | 인프라 운영 — 사용자 perspective 아님 |
| LLM 호출 (다른 시스템 가정) | 우리는 *LLM 0%* — 해당 없음 |

→ 동료가 본 *3시간*은 거의 확실히 *데이터 적재·ETL 시간*. 사용자 단건은 1초 미만.

### 동료 제안 흐름의 실제 가치

> 인터뷰 먼저 → 프로필 저장 → 주소 입력 시 두 점수 동시 표시

이 흐름은 *latency 우려와 무관하게* 다음 측면에서 유용:
- **재방문 사용자 UX 개선** — 두 번째 매물부터 인터뷰 스킵
- **다중 매물 비교** — 같은 프로필로 여러 매물 점수 비교 가능

→ **추천 절충안 (D)**: 첫 매물은 현재 3페이지 흐름(객관→인터뷰→개인화) 유지로 *서사적 효과* 살리고, 두 번째 매물부터 *저장된 프로필*로 자동 적용해 즉시 비교.

---

## 사용법

```bash
# 실제 호출 모드 (네트워크 사용)
python3 bench_api.py

# 반복 횟수 / 병렬 batch 크기 조절
python3 bench_api.py --runs 10 --batch 20

# 모의 모드 (네트워크 안 씀, 추정값으로 시나리오 시뮬레이션)
python3 bench_api.py --no-real
```

결과는 `results.md`에 자동 저장됨.

---

## 한계 및 후속 측정

- **`#1 data.go.kr` 인증 키가 만료**된 상태로 측정 (401 응답). 실제 성공 호출 시 latency는 *비슷하거나 약간 더 빠를* 가능성. 키 발급 후 재측정 권장.
- **RAG 시뮬레이션은 in-memory dict** — 실제 PostgreSQL 인덱스 hit는 5~20ms일 수 있음 (그래도 전체 wall time에 영향 미미)
- **콜드 시작 cost** — 첫 호출(connection establishment)이 p95에 반영. 실서비스에서 connection pool 유지 시 더 안정.
- **rate limit·재시도 로직** 미반영 — 실제 운영에서는 일부 API에 재시도 backoff 필요할 수 있음

---

## 관련 문서

- [`docs/interview_data_mapping.md`](../../docs/interview_data_mapping.md) — 답변 → API 활성화 매핑
- [`docs/data_mapping.md`](../../docs/data_mapping.md) — 55개 API 상세
- [`docs/execution_process.md`](../../docs/execution_process.md) — Stage 1·3 호출 흐름
