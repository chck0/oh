# Spec 33: 실거래 데이터 자동 갱신 파이프라인

> (구 spec-29 — main의 spec-29(초등학교 POI)와 충돌로 33으로 재번호)
> **상태**: Draft
> **작성일**: 2026-06-03
> **구현 브랜치**: hjkang83

---

## 1. Why (왜 만드는가)

- **MANIFESTO 원칙**: "데이터가 없으면 말하지 않는다" — 낡은 데이터로 추천하는 것은 이 원칙 위반이다.
- **Why Tree 계층**: 신뢰할 수 있는 데이터 (Middle Why 2)
- **premortem B1 🔴 최우선**: "실거래 데이터가 몇 달째 업데이트 안 되어 호가와 차이가 크다" — 현재 **대응 없음**
- **사용자가 얻는 가치**: 추천 카드의 가격이 항상 최근 3개월 실거래 기준임을 신뢰할 수 있다.

---

## 2. User Story

```
As a 아파트 매수를 검토 중인 사용자,
I want to  BADUGI의 추천 가격이 최신 실거래 기준인지 확인하고 싶다,
so that    낡은 데이터로 잘못된 의사결정을 하지 않을 수 있다.
```

---

## 3. Scope

### In-scope
- 국토부 실거래가 공개시스템 API에서 신규 거래 데이터 주기적 수집
- `trade_recent` (최근 3개월) 테이블 자동 갱신
- 마지막 갱신 날짜 UI 표시 ("데이터 기준: YYYY-MM-DD")
- 갱신 실패 시 리포트 + 알림

### Out-of-scope
- `trade_history` (3년) 전체 재수집 — 용량·시간 제약
- 실시간 갱신 (배치 1회/일 수준)
- 호가 데이터 수집 (공공데이터 원칙 위배)

---

## 4. Functional Requirements

- **F1. 수집 스크립트**: `scripts/refresh_trade_data.py`
  - 국토부 API (`MOLIT_API_KEY`) 호출
  - 최근 3개월 거래만 수집 (전체 재수집 X)
  - 신규 건만 upsert (중복 방지)

- **F2. 스케줄**: 매일 02:00 KST (트래픽 없는 시간)
  - `scripts/run_monitor_loop.py`에 통합하거나 별도 루프

- **F3. 갱신 날짜 기록**: `data_freshness` 테이블 또는 `apartments` 메타 컬럼
  - `last_trade_updated_at` 저장

- **F4. UI 표시**: `result.html` 카드 하단 또는 stats 영역
  - "실거래 기준: 2026-06-01" 형태

- **F5. 실패 감지**: `wiki/refresh_report.md` 자동 생성
  - 수집 건수, 실패 원인, 다음 실행 예정

---

## 5. Non-functional Requirements

- **성능**: 수집 1회 완료 < 5분 (배치이므로 Vercel 60초 무관)
- **신뢰성**: API 실패 시 기존 데이터 유지 (덮어쓰기 없음)
- **보안**: `MOLIT_API_KEY` 환경변수로만 관리, 코드에 하드코딩 금지
- **용량**: trade_recent는 3개월치만 유지 → 오래된 데이터 자동 만료

---

## 6. Data Model

```
trade_recent (기존 테이블, 변경 없음)
├── apt_seq:    TEXT
├── deal_date:  TEXT   -- YYYYMM
├── amount:     INTEGER
├── pyeong:     REAL
└── ...

data_freshness (신규 테이블)
├── table_name:         TEXT PRIMARY KEY  -- 'trade_recent'
├── last_updated_at:    TIMESTAMP
├── records_added:      INTEGER
└── status:             TEXT  -- 'ok' | 'fail'
```

영향받는 테이블: `trade_recent`, `data_freshness` (신규)

---

## 7. API / Interface

```python
# scripts/refresh_trade_data.py

def fetch_new_trades(year_month: str) -> list[dict]:
    """국토부 API 호출 → 신규 거래 목록 반환."""

def upsert_trades(conn, trades: list[dict]) -> int:
    """trade_recent에 upsert → 추가된 건수 반환."""

def update_freshness(conn, records_added: int, status: str) -> None:
    """data_freshness 테이블 갱신."""

def main() -> int:
    """전체 파이프라인 실행. exit 0=성공, 1=실패."""
```

---

## 8. Edge Cases

| 케이스 | 기대 동작 |
|--------|-----------|
| `MOLIT_API_KEY` 없음 | 즉시 종료 + 리포트에 오류 기록 |
| API 응답 없음 / 타임아웃 | 기존 데이터 유지, 실패 리포트 |
| 중복 거래 데이터 | upsert로 무시 |
| 국토부 API 스펙 변경 | 파싱 오류 → 리포트에 raw 응답 저장 |
| Supabase 연결 실패 | 로컬 SQLite로 fallback 시도 |

---

## 9. Acceptance Criteria

- [ ] AC1: `python scripts/refresh_trade_data.py` 실행 시 신규 거래 데이터 수집
- [ ] AC2: `trade_recent` 테이블에 최근 3개월 데이터가 갱신됨
- [ ] AC3: `data_freshness` 테이블에 마지막 갱신 시각 기록
- [ ] AC4: 결과 페이지에 "실거래 기준: YYYY-MM-DD" 표시
- [ ] AC5: API 실패 시 기존 데이터 보존 + `wiki/refresh_report.md` 생성
- [ ] AC6: 기존 pytest 388+ passed 유지

---

## 10. Open Questions

- Q1: `MOLIT_API_KEY` 보유 여부 확인 필요 — 없으면 발급 선행
- Q2: `data_freshness` 테이블 신규 생성 → Supabase SQL Editor 수동 실행 필요
- Q3: Docker 모니터링 루프와 통합할지, 별도 스크립트로 운영할지
