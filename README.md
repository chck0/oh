# BADUGI — 직장 주소 기반 아파트 추천 서비스

> "부동산 잘 아는 친구가 옆에서 카톡으로 추천해주는" 경험

직장 주소와 조건(통근시간·예산·평형)을 입력하면 추천 단지를 지도 + 카드로 보여주고,
AI 친구가 각 단지를 솔직하게 한 줄로 설명해준다.

배포: **Vercel (서버리스)** + **Supabase Postgres**

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 통근시간 기반 검색 | 직장 주소 → ODsay 대중교통 경로 → 통근버킷 × 평형 매트릭스 추천 |
| 맞벌이 교집합 검색 | 두 직장 반경 교집합 내 단지만 추천 |
| 친구 채팅 | Claude Opus 기반 Q&A (시세·학군·투자 분석), 웹 검색 tool_use, 이미지·PDF 첨부 분석 |
| 단지 상세 분석 | 시세 차트·실거래·도보 시설·통근경로 상세 |
| 아파트 직접 검색 | 결과 화면에서 단지명 자동완성 검색 → 지도 핀 + 상세 패널 |
| 즐겨찾기 & 비교 | ♥ 저장 후 2개 단지 나란히 비교 |

---

## 폴더 구조

```
app/           # FastAPI 백엔드 (핵심 비즈니스 로직)
  main.py      # FastAPI 진입점 + 미들웨어 + 진단 엔드포인트
  search.py    # 검색·상세·채팅 API 라우터
  ai.py        # 추천 로직 + Claude 코멘트 생성
  transit.py   # ODsay 멀티키 병렬 호출 + DB 캐싱
  workplaces.py# Kakao 주소 정규화 + wp_id 발급
  db.py        # SQLite ↔ Postgres 이중 어댑터
  portable.py  # DB 비호환 로직 Python 구현

api/           # Vercel 서버리스 진입점 (api/index.py)
web/           # 프론트엔드 (Vanilla JS + Kakao Maps)
  search.html  # 검색 조건 입력 화면
  result.html  # 지도 + 카드 + 친구 채팅 패널
scripts/       # 데이터 파이프라인 + DB 마이그레이션
docs/          # 설계 문서 (spec, manifesto, premortem, whytree)
config.py      # 중앙 환경변수 관리
vercel.json    # Vercel 배포 설정
requirements.txt
```

---

## 로컬 실행

```bash
# 1) 의존성 설치
pip install -r requirements.txt

# 2) 환경변수 설정 (.env 또는 shell export)
export KAKAO_REST_API_KEY=...
export ODSAY_KEY_1=...
export ODSAY_REFERER_1=...
export ANTHROPIC_API_KEY=...
# DB_PATH=data/apartment.db  # SQLite (DATABASE_URL 없을 때 자동)

# 3) 검증
python config.py

# 4) 서버 기동
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/
```

---

## 진단 엔드포인트

| 엔드포인트 | 용도 |
|---|---|
| `GET /health` | 서버 상태 체크 |
| `GET /api/_debug` | 환경변수·DB 행 수·연결 상태 |
| `GET /api/_test_odsay` | ODsay 키 실제 호출 테스트 |
| `GET /api/_test_kakao` | Kakao REST API 테스트 |

---

## 주요 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/search` | 직장 주소 → 추천 카드 |
| GET | `/api/apt/{seq}/detail` | 단지 상세 (시세·실거래·POI) |
| GET | `/api/apt/{seq}/routes` | 통근 경로 옵션 |
| POST | `/api/apt/{seq}/chat` | 친구 채팅 (이미지·PDF 첨부 지원) |
| GET | `/api/search/apt-lookup` | 단지명 자동완성 검색 |

---

## 환경변수

```bash
# 런타임 필수
DATABASE_URL=postgresql://...        # Supabase (pgBouncer 6543)
KAKAO_REST_API_KEY=...
ODSAY_KEY_1=..., ODSAY_REFERER_1=... # 최대 20개 키
ANTHROPIC_API_KEY=...

# 로컬 dev (DATABASE_URL 없을 때)
DB_PATH=data/apartment.db

# 스크립트 전용
VWORLD_API_KEY=...
MOLIT_API_KEY=...
```

---

## 테스트

```bash
python -m pytest --tb=short -q
# 387 tests (2026-05-31 기준)
```

---

## API 키 출처

| 키 | 용도 | 발급처 |
|---|---|---|
| KAKAO_REST_API_KEY | 주소 → 좌표 | developers.kakao.com |
| ODSAY_KEY_N | 대중교통 경로 | lab.odsay.com |
| ANTHROPIC_API_KEY | Claude 코멘트·채팅 | console.anthropic.com |
| VWORLD_API_KEY | 지오코딩 (스크립트) | vworld.kr |
| MOLIT_API_KEY | 실거래·건축물대장 (스크립트) | data.go.kr |
