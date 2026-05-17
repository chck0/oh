# real_estate — 아파트 검색 서비스

통근시간·예산·평형 조건으로 아파트 단지를 검색하는 서비스.

## 폴더 구조

```
real_estate/
├── config.py                 # 중앙 설정 (.env 로더)
├── .env                      # API 키 (커밋 금지)
├── .env.example              # 환경변수 템플릿
├── requirements.txt
│
├── data/                     # DB·캐시·백업 (git ignore)
│   ├── apartment.db
│   └── backup/
│
├── sandbox/                  # 작업용 임시 코드 (git ignore)
│                             # 데이터 보면서 수정·수정 하는 단계의 실험 코드
│                             # 안정화되면 scripts/로 승격
│
├── scripts/                  # 데이터 파이프라인 (번호 순서대로 실행)
│   ├── 01_fetch_kapt_complexes.py    # 공동주택 단지 마스터
│   ├── 02_fetch_apartments_v4.py     # V4 단지 상세
│   ├── 03_geocode.py                 # 좌표
│   ├── 04_fetch_trade_recent.py      # 3개월 실거래
│   ├── 05_fetch_trade_history.py     # 3년 실거래
│   ├── 06_fetch_building_register.py # 건축물대장
│   ├── 07_supplement_no_data.py      # 카카오 도로명→지번 보완
│   ├── 08_classify_buildings.py      # is_apt 분류
│   ├── 10_reset_transit_tables.py    # transit 캐시 초기화
│   ├── 11_fetch_transit.py           # ODsay 호출
│   └── 12_load_transit_routes.py     # transit_routes 적재
│
├── app/                      # FastAPI 백엔드
│   ├── main.py               # uvicorn 진입점
│   ├── db.py                 # SQLite 연결
│   ├── models.py             # Pydantic 스키마
│   ├── search.py             # 검색 API 라우터
│   └── transit.py            # 실시간 transit (캐시 미스)
│
├── web/                      # 정적 프론트엔드
│   ├── index.html
│   └── static/
│
├── logs/
└── deploy/                   # EC2 nginx / systemd 설정
```

## 초기 설정

```bash
# 1) 의존성 설치
pip install -r requirements.txt

# 2) .env 작성
cp .env.example .env
# 각 API 키 채우기

# 3) config 로드 확인
python config.py
```

## 데이터 파이프라인 실행 (처음 1회)

```bash
python scripts/01_fetch_kapt_complexes.py
python scripts/02_fetch_apartments_v4.py
python scripts/03_geocode.py
python scripts/04_fetch_trade_recent.py
python scripts/05_fetch_trade_history.py
python scripts/06_fetch_building_register.py
python scripts/07_supplement_no_data.py
python scripts/08_classify_buildings.py
```

## 서버 실행

```bash
# 개발
uvicorn app.main:app --reload --port 8000

# 운영 (EC2 systemd)
sudo systemctl start real_estate
```

## API 키 출처

| 키 | 용도 | 발급처 |
|---|---|---|
| KAKAO_REST_API_KEY | 도로명→지번 변환 | developers.kakao.com |
| VWORLD_API_KEY | 지오코딩 | vworld.kr |
| MOLIT_API_KEY | 실거래·V4·건축물대장 | data.go.kr |
| ODSAY_KEY_N | 대중교통 길찾기 | lab.odsay.com |
