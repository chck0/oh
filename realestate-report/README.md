# VerifyHome — 시세 분석 웹앱

실거래 데이터 기반으로 아파트 시세를 분석하는 웹 프로토타입입니다.

## 로컬 실행 (3단계)

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에 아래 키 입력:
#   ANTHROPIC_API_KEY   — claude.ai/settings 에서 발급
#   DATA_GO_KR_API_KEY  — data.go.kr 아파트매매 실거래 API 신청
#   JUSO_CONFIRM_KEY    — business.juso.go.kr 도로명주소 API 신청

# 3. API 서버 실행
uvicorn src.market_api:app --reload --port 8000
```

서버 실행 후 브라우저에서 `realestate-report/page0-web.html` 파일을 직접 열면 됩니다.

> **API 키 없이도 실행 가능** — 키가 없으면 mock 데이터로 동작합니다.
> 챗봇(`ANTHROPIC_API_KEY`)과 실거래 데이터(`DATA_GO_KR_API_KEY`)는 해당 키가 있어야 작동합니다.
