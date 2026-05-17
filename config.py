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
from pathlib import Path
from dotenv import load_dotenv

# 이 파일 기준으로 .env 경로 고정 → 어느 디렉토리에서 실행해도 동작
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / '.env', override=True)


def _require(key: str) -> str:
    """필수 환경변수 — 없으면 즉시 에러 (오타/누락 조기 감지)"""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"[config] 필수 환경변수 누락: {key}  →  .env 파일을 확인하세요")
    return val


def _optional(key: str, default: str = '') -> str:
    return os.getenv(key, default)


# scripts/ 데이터 파이프라인 전용 키는 런타임(Vercel)엔 없어도 OK.
# 런타임에서 _require_runtime=True 인 키만 강제로 요구.
def _require_runtime(key: str) -> str:
    """런타임 필수 — Vercel 함수에서 동작에 꼭 필요한 키만 _require로."""
    return _require(key)


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

    # ── Anthropic Claude API (런타임에서 LLM 코멘트 생성에 사용) ─
    ANTHROPIC_API_KEY: str = _optional('ANTHROPIC_API_KEY')

    # ── Supabase / Postgres ──────────────────────────────────
    # DATABASE_URL이 있으면 app/db.py가 Supabase 모드로 전환
    DATABASE_URL: str = _optional('DATABASE_URL') or _optional('SUPABASE_DB_URL')

    # ── ODsay — KEY_N / REFERER_N 쌍을 리스트로 자동 조립 ────
    # 런타임 필수 — transit 캐시 미스 시 호출.
    # ODSAY_KEY_1 ~ ODSAY_KEY_20 까지 스캔하고 빈 번호는 건너뜀
    # (망가진 키 1개 삭제해도 뒤 번호 살릴 수 있게 gap 허용)
    @property
    def ODSAY_KEYS(self) -> list[dict]:
        keys = []
        for i in range(1, 21):
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
    # 환경변수 DB_PATH가 상대경로면 PROJECT_ROOT 기준으로 해석
    @property
    def DB_PATH(self) -> str:
        raw = _optional('DB_PATH', 'data/apartment.db')
        p = Path(raw)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return str(p)


cfg = _Config()


# ── 직접 실행 시 로드 상태 확인 ──────────────────────────────
if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print('=== config 로드 확인 ===')
    print(f'PROJECT_ROOT       : {cfg.PROJECT_ROOT}')
    print(f'DB_PATH            : {cfg.DB_PATH}')
    print(f'KAKAO_REST_API_KEY : {cfg.KAKAO_REST_API_KEY[:6]}...')
    print(f'VWORLD_API_KEY     : {cfg.VWORLD_API_KEY[:6]}...')
    print(f'MOLIT_API_KEY      : {cfg.MOLIT_API_KEY[:6]}...')
    print(f'ODSAY_KEYS         : {len(cfg.ODSAY_KEYS)}개')
    for i, k in enumerate(cfg.ODSAY_KEYS, 1):
        print(f'  [{i}] {k["key"][:6]}...  {k["referer"]}')
