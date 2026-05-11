## 프로젝트 개요

**점찍어둔 아파트 한 채를 5개 도메인 + 사용자 가치관으로 검증하는 2차 의견(Second Opinion) 도구.**

- 타깃: 민준 (37세, 생애 첫 주택 구매자, 정보 비대칭이 가장 심한 시점)
- 흐름: 매물 주소 → 5장 카드 객관 점수 → 사용자 인터뷰 → 3 에이전트 가중치 토론 → 사용자 가중치 조정 → 종합 점수
- 총 사용자 소요 시간: **약 5분**

→ 상세: `docs/README.md`, `docs/manifesto.md`, `docs/persona.md`

## 작업 방식

### 1. Forest First, Then Trees

- 새 작업을 시작할 때 **전체 그림(목표, 범위, 영향받는 파일)을 먼저 파악**한 뒤 세부 구현에 들어간다.
- 코드를 바로 작성하지 말고, 어떤 파일들이 변경되는지 먼저 정리해서 보여준다.
- 큰 작업은 Phase 단위로 나눠서 단계적으로 진행한다.

### 2. 확인하면서 진행 (Interview & Check)

- 모호한 요청이 들어오면 **추정으로 진행하지 말고 질문**한다.
- 각 단계 완료 후 결과를 요약해서 보고하고, 다음 단계로 넘어가기 전에 사용자 확인을 받는다.
- 단, "바로 반영해줘", "계속 진행하자" 같은 명확한 지시에는 즉시 실행한다.

### 3. 항상 테스트 → 커밋

- **커밋 전에 반드시 `pytest tests/ -v` 전체 테스트를 실행**한다.
- 테스트 실패 시 수정 후 재실행하여 전체 통과를 확인한 뒤 커밋한다.
- 새 기능 추가 시 해당 테스트도 함께 작성한다.

### 4. Git 워크플로우

- **세션 시작 시 항상 `git pull origin main`** — GitHub 웹에서 수정한 내용을 놓치지 않는다.
- 작업 브랜치에서 개발 → PR 생성 → **squash merge**로 main에 반영.
- 커밋 메시지는 conventional commits 스타일: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- 푸시 실패 시 rebase 후 재시도. 네트워크 오류는 최대 4회 지수 백오프 재시도.
- 각 스테이지 완료 후 **바로 커밋+푸시** — 다음 스테이지를 시작하기 전에 현재 작업을 안전하게 저장.

## 기술 스택

- **언어**: Python 3.10+
- **비동기**: `asyncio` + `aiohttp` (5장 카드 병렬 분석)
- **LLM**: Anthropic Claude API (`claude-sonnet-4-6`), `AsyncAnthropic` — 자연어 다듬기·분류만 (점수 산출 0%)
- **데이터**: `PublicDataReader`, `pandas`, `scikit-learn`, `numpy`
- **캐싱**: Redis 또는 `diskcache`
- **프론트엔드**: Streamlit + Plotly
- **테스트**: pytest, API 키 없이 전체 로직 검증
- **의존성**: `requirements.txt` 참조

## 프로젝트 구조

```
src/           # 소스 코드 (main.py CLI, app.py Streamlit UI)
agents/        # 에이전트 명세 (옹호·반대·중립 룰)
tests/         # pytest 테스트 스위트
docs/          # 설계 문서 (manifesto, persona, data_mapping, execution_process 등)
meetings/      # 미팅 자료
```

## 핵심 규칙

1. **AI는 결정 대신해주지 않는다** — 분석만, 판단은 사용자에게.
2. **100% 공공 데이터** — 직방·호갱노노·리파인 의존 0%. 정부·공공기관 OpenAPI + 한국부동산원 RAG만.
3. **개인정보 최소화** — 자산·소득·대출·신용 안 받는다. 매물 객관 검증만.
4. **LLM 할루시네이션 0%** — 점수·가중치·트리거는 룰로 산출. LLM은 자연어 다듬기·분류에만 (상세: `docs/llm_policy.md`).
5. **SLC (Simple, Lovable, Complete)** — 시연 시점에 모든 카드가 완결 작동해야 한다. "추후 검증" 같은 연기형 약속을 하지 않는다. 들어가는 건 다 작동, 안 들어가는 건 명시적으로 시스템 범위 밖으로 선언한다.
6. **데이터로 못 잡는 건 아웃풋에 안 담는다** — 약속을 줄여서 약속을 지킨다.
7. **모든 수치에는 출처를 명시**한다.

## 시스템 범위

| ✅ 시스템 안 | ❌ 시스템 밖 (사유) |
|---|---|
| 매물 단지 단위 객관 검증 (5장 카드) | 자산·대출·DSR 시뮬레이션 (개인정보) |
| 호가 vs 실거래가 회귀 잔차 분석 | 매물 호 단위 결함 (층간소음·누수 등, 임장 위임) |
| 입지·생활편의·미래가치·리스크 정량화 | 권리관계·법무 자문 (인터넷등기소 700원 직접) |
| 공식 발표 기반 호재 의존도 분해 | 호재 실현 예언 / 5~10년 단일 가격 예측 |
| 사용자 가치관 기반 가중치 토론 | 자연재해 카드 (도시 매물 의미 약함) |

## 7 Stage 흐름

```
1. 매물 식별         → 주소 표준화 → HSMP_INNB 매핑 (~2초)
2. 기본 인터뷰       → 회사 위치·가족·우선순위 (3~4 질문, ~1분)
3. 5장 카드 분석     → asyncio.gather 병렬, 별점 산출 (~30초~1분)
4. 가중치 인터뷰     → 5문항 (보유기간·학군·우선순위 등, ~1~2분)
5. 3 에이전트 토론   → 옹호·반대·중립 룰 기반 가중치 추천 (~1초)
6. 사용자 조정       → 슬라이더로 가중치 직접 조정, 종합 점수 실시간 재계산
7. 종합 점수 + 가이드 → 최종 결과 (매수 결정은 사용자)
```

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `src/cards/price.py` | Card 1 시세 — 회귀 잔차·환원율 |
| `src/cards/location.py` | Card 2 입지 — 도보 거리·환승·학교 |
| `src/cards/lifestyle.py` | Card 3 생활편의 — 인프라 인접도 |
| `src/cards/future.py` | Card 4 미래가치 — 호재 의존도·정비사업·인구 |
| `src/cards/risk.py` | Card 5 리스크 — 노후·환경·소음·표고 |
| `src/orchestrator.py` | 7 Stage 오케스트레이터 (asyncio.gather 병렬) |
| `src/agents.py` | 옹호·반대·중립 에이전트 룰 |
| `src/interview.py` | 기본 인터뷰 + 가중치 결정 인터뷰 |
| `src/weight.py` | 인터뷰 답변 → 가중치 룰 매트릭스 |
| `src/llm.py` | LLM 허용 영역 (분류·다듬기·플레이스홀더) + 검증·fallback |
| `src/data/fetcher.py` | 공공데이터 API 호출 + 캐싱 |
| `src/app.py` | Streamlit Web UI |

## LLM 사용 원칙 요약

- **허용**: 분류(사전 옵션 중 선택), 자연어 다듬기(숫자·고유명사 유지), 플레이스홀더 채우기
- **금지**: 점수 산출, 가중치 산출, 트리거 판정, 추론·예언, 자유 형식 발언 생성
- `temperature=0`, 출력 자동 검증, 실패 시 룰 fallback 필수
- 상세: `docs/llm_policy.md`

## 데이터 자산

- **공공데이터포털 OpenAPI**: 29개 (data.go.kr, 서비스키 1개)
- **별도 사이트 API**: 8개 (juso·vworld·NEIS·ECOS·ODsay·T맵 등)
- **RAG 데이터**: 20개 (한국부동산원 16 + 공간정보산업진흥원 2 + 데이터웨이 2)
- **합계: 55개**
- **마스터 키**: `HSMP_INNB` (한국부동산원 단지고유번호 14자리)

→ 상세: `docs/data_mapping.md`

## 테스트 실행

```bash
pytest tests/ -v              # 전체 테스트
pytest tests/test_e2e.py -v   # E2E 파이프라인 테스트
python src/demo_mock.py       # API 키 없이 Mock 데모
streamlit run src/app.py      # Streamlit Web UI
```

## 세션 관리

- 세션 시작 시 **반드시 `git fetch && git pull origin main`** 먼저 실행.
- 최근 커밋 5개를 확인하고, 이전 세션에서 중단된 작업이 있는지 파악한 후 작업을 시작한다.
- 한 세션에서 1~2개 스테이지만 완결하는 것을 목표로 한다 — 4개를 시작하는 것보다 2개를 완결하는 게 낫다.

## 환경 변수

- `ANTHROPIC_API_KEY`: LLM 자연어 다듬기·분류에 필요. 없으면 룰 fallback으로 동작.
- `DATA_GO_KR_API_KEY`: 공공데이터포털 OpenAPI 호출에 필요. 없으면 샘플 데이터 fallback.
- API 키가 없을 때는 즉시 사용자에게 알리고, 조용히 mock으로 대체하지 않는다.


## 의사소통 언어

- 한국어를 기본으로 사용한다.
- 커밋 메시지와 PR 제목은 한국어 또는 영어 모두 가능.
