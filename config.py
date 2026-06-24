"""
config.py — 프로젝트 전체 설정 중앙 관리

사용법:
    from config import cfg

    cfg.KAKAO_REST_API_KEY   # 카카오 REST 키
    cfg.MOLIT_API_KEY        # 국토부 키
    cfg.ODSAY_KEYS           # ODsay 키 리스트 [{'key':..., 'referer':...}, ...]
    cfg.DB_PATH              # DB 파일 절대경로
"""
import os
from functools import cached_property
from pathlib import Path
from dotenv import load_dotenv

# 이 파일 기준으로 .env 경로 고정 → 어느 디렉토리에서 실행해도 동작
# override=False: OS 환경변수(Vercel 대시보드 설정값)가 .env보다 우선
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / '.env', override=False)


def _require(key: str) -> str:
    """필수 환경변수 — 없으면 즉시 에러 (오타/누락 조기 감지)"""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"[config] 필수 환경변수 누락: {key}  →  .env 파일을 확인하세요")
    return val


def _optional(key: str, default: str = '') -> str:
    return os.getenv(key, default)


def _optional_int(key: str, default: int) -> int:
    """정수형 환경변수 — 없거나 파싱 불가면 default 반환."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _optional_float(key: str, default: float) -> float:
    """실수형 환경변수 — 없거나 파싱 불가면 default 반환."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# scripts/ 데이터 파이프라인 전용 키는 런타임(Vercel)엔 없어도 OK.
# 런타임에서 _require_runtime=True 인 키만 강제로 요구.
def _require_runtime(key: str) -> str:
    """런타임 필수 — Vercel 함수에서 동작에 꼭 필요한 키만 _require로."""
    return _require(key)


def _is_pg_url(url: str) -> bool:
    """postgresql:// 또는 postgres:// 로 시작하면 True — 파일 경로와 구분."""
    return url.startswith(('postgresql://', 'postgres://'))


class _Config:
    PROJECT_ROOT: Path = PROJECT_ROOT

    # ── 카카오 (런타임 필수: workplaces에서 주소 변환) ───────
    KAKAO_REST_API_KEY: str = _require('KAKAO_REST_API_KEY')
    KAKAO_JS_KEY:       str = _optional('KAKAO_JS_KEY')
    KAKAO_NATIVE_KEY:   str = _optional('KAKAO_NATIVE_KEY')

    # ── Vworld (scripts 전용 — 런타임 미사용) ────────────────
    VWORLD_API_KEY: str = _optional('VWORLD_API_KEY')

    # ── 국토부 (scripts 전용 — 런타임 미사용) ────────────────
    MOLIT_API_KEY: str = _optional('MOLIT_API_KEY')

    # ── NEIS 교육정보 개방 포털 (scripts 전용 — 초등학교 수집) ─
    NEIS_API_KEY: str = _optional('NEIS_API_KEY')

    # ── Anthropic Claude API (런타임에서 LLM 코멘트 생성에 사용) ─
    ANTHROPIC_API_KEY: str = _optional('ANTHROPIC_API_KEY')

    # ── Claude 모델명 — 환경변수로 override 가능 ─────────────────
    # 기본값은 현재 사용 중인 dated 버전. 모델 retire/업그레이드 시
    # 코드 수정 없이 .env 또는 Vercel 대시보드에서 변경 가능.
    # 예) CLAUDE_SONNET_MODEL=claude-sonnet-4-7
    SONNET_MODEL: str = _optional('CLAUDE_SONNET_MODEL', 'claude-sonnet-4-5-20250929')
    HAIKU_MODEL:  str = _optional('CLAUDE_HAIKU_MODEL',  'claude-haiku-4-5-20251001')
    OPUS_MODEL:   str = _optional('CLAUDE_OPUS_MODEL',   'claude-opus-4-8')

    # ── Supabase / Postgres ──────────────────────────────────
    # DATABASE_URL이 있으면 app/db.py가 Supabase 모드로 전환
    DATABASE_URL: str = _optional('DATABASE_URL') or _optional('SUPABASE_DB_URL')

    # ── 검색 정책 상수 ────────────────────────────────────────
    # 코드에 박혀 있던 매직넘버를 한 곳에서 관리.
    # .env 또는 Vercel 대시보드에서 override 가능.

    # 통근시간 여유분 (사용자 입력에서 차감 → 반경 계산에 사용)
    COMMUTE_BUFFER_MIN: int   = _optional_int('COMMUTE_BUFFER_MIN', 10)

    # Vercel 플랜별 타임아웃 예산 (Hobby=60s, Pro=300s)
    WALL_CLOCK_BUDGET_S:  int = _optional_int('WALL_CLOCK_BUDGET_S',  50)
    ODSAY_HARD_TIMEOUT_S: int = _optional_int('ODSAY_HARD_TIMEOUT_S', 30)
    MAX_FETCH_CELLS:      int = _optional_int('MAX_FETCH_CELLS',      200)

    # 반경 계산에 사용하는 평균 대중교통 속도 (km/h)
    AVG_SPEED_KMH: float = _optional_float('AVG_SPEED_KMH', 20.0)

    # POI 도보 거리 상한 (분) — 단지 상세·채팅 화면에서 도보 시설 필터
    POI_WALK_MAX_MIN: int = _optional_int('POI_WALK_MAX_MIN', 10)

    # 인메모리 캐시 TTL (초)
    APT_CACHE_TTL_S:  int = _optional_int('APT_CACHE_TTL_S',  300)
    CHAT_CACHE_TTL_S: int = _optional_int('CHAT_CACHE_TTL_S', 3600)

    # comments: /api/comments/generate 1회 요청에서 동기로 처리하는 청크 크기
    # (추천 Sonnet + 일반 Haiku). 청크 단위로 생성·commit 하며 시간 예산까지 반복.
    BG_COMMENTS_MAX_REC: int = _optional_int('BG_COMMENTS_MAX_REC', 8)
    BG_COMMENTS_MAX_REG: int = _optional_int('BG_COMMENTS_MAX_REG', 16)
    # 1회 요청의 동기 생성 시간 예산(초). Vercel maxDuration(60s)보다 충분히 작게.
    COMMENTS_TIME_BUDGET_S: int = _optional_int('COMMENTS_TIME_BUDGET_S', 35)

    @property
    def USE_PG(self) -> bool:
        """DATABASE_URL이 PostgreSQL URL일 때만 True.
        파일 경로(SQLite 모드)가 설정된 경우 False → Supabase 완전 차단."""
        return bool(self.DATABASE_URL) and _is_pg_url(self.DATABASE_URL)

    @property
    def IS_SERVERLESS(self) -> bool:
        """Vercel 환경이면 True (VERCEL 환경변수 자동 세팅됨)."""
        return bool(os.getenv('VERCEL'))

    # ── ODsay — KEY_N / REFERER_N 쌍을 리스트로 자동 조립 ────
    # 런타임 필수 — transit 캐시 미스 시 호출.
    # ODSAY_KEY_1 ~ ODSAY_KEY_30 까지 스캔하고 빈 번호는 건너뜀
    # (망가진 키 1개 삭제해도 뒤 번호 살릴 수 있게 gap 허용)
    @cached_property
    def ODSAY_KEYS(self) -> list[dict]:
        keys = []
        for i in range(1, 31):
            k = os.getenv(f'ODSAY_KEY_{i}')
            if not k:
                continue
            keys.append({
                'key':     k,
                'referer': os.getenv(f'ODSAY_REFERER_{i}', ''),
            })
        if not keys:
            raise EnvironmentError('[config] ODsay 키가 없습니다 (ODSAY_KEY_1 이상 필요)')
        return keys

    # ── DB ───────────────────────────────────────────────────
    # DATABASE_URL이 파일 경로면 그걸 SQLite 경로로 사용.
    # 아니면 DB_PATH 환경변수(기본: data/apartment.db) 사용.
    # 상대경로는 PROJECT_ROOT 기준으로 해석.
    @property
    def DB_PATH(self) -> str:
        if self.DATABASE_URL and not _is_pg_url(self.DATABASE_URL):
            p = Path(self.DATABASE_URL)
            return str(p if p.is_absolute() else PROJECT_ROOT / p)
        raw = _optional('DB_PATH', 'data/apartment.db')
        p = Path(raw)
        return str(p if p.is_absolute() else PROJECT_ROOT / p)


cfg = _Config()


# ── 직접 실행 시 로드 상태 확인 ──────────────────────────────
if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[union-attr]
    print('=== config 로드 확인 ===')
    print(f'PROJECT_ROOT       : {cfg.PROJECT_ROOT}')
    print(f'DB_PATH            : {cfg.DB_PATH}')
    print(f'KAKAO_REST_API_KEY : {cfg.KAKAO_REST_API_KEY[:6]}...')
    print(f'VWORLD_API_KEY     : {cfg.VWORLD_API_KEY[:6]}...')
    print(f'MOLIT_API_KEY      : {cfg.MOLIT_API_KEY[:6]}...')
    print(f'ODSAY_KEYS         : {len(cfg.ODSAY_KEYS)}개')
    for i, k in enumerate(cfg.ODSAY_KEYS, 1):
        print(f'  [{i}] {k["key"][:6]}...  {k["referer"]}')
    print(f'SONNET_MODEL       : {cfg.SONNET_MODEL}')
    print(f'HAIKU_MODEL        : {cfg.HAIKU_MODEL}')
    print(f'OPUS_MODEL         : {cfg.OPUS_MODEL}')
    print(f'--- 정책 상수 ---')
    print(f'COMMUTE_BUFFER_MIN : {cfg.COMMUTE_BUFFER_MIN}')
    print(f'WALL_CLOCK_BUDGET_S: {cfg.WALL_CLOCK_BUDGET_S}')
    print(f'MAX_FETCH_CELLS    : {cfg.MAX_FETCH_CELLS}')
    print(f'AVG_SPEED_KMH      : {cfg.AVG_SPEED_KMH}')
    print(f'POI_WALK_MAX_MIN   : {cfg.POI_WALK_MAX_MIN}')
    print(f'APT_CACHE_TTL_S    : {cfg.APT_CACHE_TTL_S}')
    print(f'CHAT_CACHE_TTL_S   : {cfg.CHAT_CACHE_TTL_S}')
