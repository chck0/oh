"""
app/ai.py — 추천 로직 + 통계 + Claude Haiku 코멘트

[새 컨셉]
- 카드 단위 = (apt_seq, pyeong_type)  ← 같은 단지 두 평형이면 카드 2장
- 통근시간 버킷 (10분 단위) × 평형 매트릭스에서 각 슬롯의 최저가 1개를 '추천'으로 표시
- 같은 단지가 여러 슬롯에 걸리면 1번만 등장
- 통계: 통근-가격 곡선, 평형별 시세, 연식 분포
- 추천 카드 → 균형 잡힌 긴 코멘트 (장점+단점 솔직하게)
- 나머지 카드 → LLM 호출 안 함

핵심 함수:
    build_recommendations(cards, max_minutes) -> dict
    build_stats(cards, buckets) -> dict
    build_comments(recommended_cards, all_cards, wp_label) -> dict[apt_pt_key, comment]
"""
import asyncio
from datetime import date
import anthropic
from config import cfg

# ── Anthropic 클라이언트 ─────────────────────────────────────
_client: anthropic.AsyncAnthropic | None = None

def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=cfg.ANTHROPIC_API_KEY)
    return _client


# ── 모델 분리 ────────────────────────────────────────────────
# 추천 카드 (소수, 긴 코멘트, 균형 잡힌 시각) → Sonnet
# 일반 카드 (다수, 한 줄 평) → Haiku (저렴, 빠름)
# dated 버전 사용 (alias가 권한/접근 이슈로 실패하는 경우 대비)
SONNET_MODEL = 'claude-sonnet-4-5-20250929'
HAIKU_MODEL = 'claude-haiku-4-5-20251001'

# 일반 카드 동시 호출 상한 (Anthropic rate limit 안전치)
REGULAR_CONCURRENCY = 8


# ═══════════════════════════════════════════════════════════════
#  통근 버킷 정의
# ═══════════════════════════════════════════════════════════════
def make_buckets(max_minutes: int) -> list[tuple[int, int]]:
    """
    통근시간 버킷: 0~30분, 30~40분, 40~50분, 50~max
    """
    bs = [(0, 30)]
    start = 30
    while start < max_minutes:
        end = min(start + 10, max_minutes)
        bs.append((start, end))
        start = end
    return bs


def bucket_label(s: int, e: int) -> str:
    if s == 0:
        return f"{e}분 이내"
    return f"{s}~{e}분"


def assign_bucket(t: int, buckets: list[tuple[int, int]]) -> int:
    for i, (s, e) in enumerate(buckets):
        if s < t <= e or (i == 0 and t <= e):
            return i
    return len(buckets) - 1


def card_key(c: dict) -> str:
    """카드 고유 키 = apt_seq:pyeong_type"""
    return f"{c['apt_seq']}:{c.get('pyeong_type','')}"


# ═══════════════════════════════════════════════════════════════
#  추천 로직 — 통근 버킷 × 평형 매트릭스
# ═══════════════════════════════════════════════════════════════
def build_recommendations(cards: list[dict], max_minutes: int) -> dict:
    """
    카드에 다음 필드 추가:
      - bucket_idx, bucket_label
      - is_recommended (bool)
      - pick_reason (str)         : 추천 이유 (로직 기반, LLM 아님)
      - price_diff_vs_fastest     : 같은 평형 최단버킷 최저가 대비 차액 (만원)

    각 (버킷 × 평형) 슬롯 → 최저가 1개를 추천.
    같은 단지(apt_seq)가 여러 슬롯에 등장하면 첫 번째 슬롯에만 추천 표시.
    """
    if not cards:
        return {'buckets': [], 'cards': []}

    buckets = make_buckets(max_minutes)

    # 카드에 버킷 부여
    for c in cards:
        c['bucket_idx'] = assign_bucket(c['total_time_min'], buckets)
        c['bucket_label'] = bucket_label(*buckets[c['bucket_idx']])

    # 슬롯 그룹화
    slots: dict[tuple[int, str], list[dict]] = {}
    for c in cards:
        key = (c['bucket_idx'], c['pyeong_type'])
        slots.setdefault(key, []).append(c)

    # 평형별 최단버킷 최저가 (차액 비교 기준)
    pyeong_types = sorted(set(c['pyeong_type'] for c in cards))
    baseline_by_pt: dict[str, int] = {}
    for pt in pyeong_types:
        for bi in range(len(buckets)):
            items = slots.get((bi, pt), [])
            if items:
                baseline_by_pt[pt] = min(c['price_low'] for c in items)
                break

    # 슬롯 순회: 버킷 오름차순 → 평형 순으로 추천 1개씩 선정
    recommended_seqs: set[str] = set()
    for bi in range(len(buckets)):
        for pt in pyeong_types:
            key = (bi, pt)
            if key not in slots:
                continue
            items = sorted(slots[key], key=lambda c: c['price_low'])
            for c in items:
                if c['apt_seq'] in recommended_seqs:
                    continue
                # 추천 결정
                c['is_recommended'] = True
                # 차액
                base = baseline_by_pt.get(pt)
                if base is not None and c['price_low'] != base:
                    c['price_diff_vs_fastest'] = c['price_low'] - base
                else:
                    c['price_diff_vs_fastest'] = 0
                # 픽 사유 (로직 기반)
                c['pick_reason'] = _make_pick_reason(c, items, base)
                recommended_seqs.add(c['apt_seq'])
                break

    # 추천 외
    for c in cards:
        c.setdefault('is_recommended', False)

    return {
        'buckets': [
            {'idx': i, 'min': s, 'max': e, 'label': bucket_label(s, e)}
            for i, (s, e) in enumerate(buckets)
        ],
        'cards': cards,
    }


def _make_pick_reason(c: dict, slot_items: list[dict], baseline_price: int | None) -> str:
    """추천 이유 한 줄 (LLM 아님, 로직 기반)"""
    bl = c.get('bucket_label', '')
    pt = c.get('pyeong_type', '')
    slot_size = len(slot_items)

    # 같은 평형 최단버킷 대비 차액
    diff = c.get('price_diff_vs_fastest', 0)
    if diff < 0:
        # 더 쌈 (최단버킷 기준값보다 저렴 — 사실 이건 발생 거의 안 함)
        return f"'{bl} · {pt}' 슬롯에서 최저가 ({slot_size}곳 중)"
    elif diff > 0:
        억 = abs(diff) // 10000
        천 = (abs(diff) % 10000) // 1000
        diff_str = f"{억}억" if 천 == 0 else f"{억}억 {천}천"
        return f"'{bl} · {pt}' 중 최저가. 같은 평형 최단권보다 {diff_str} 저렴"
    else:
        # baseline 자체 (최단버킷 추천 카드)
        return f"'{bl} · {pt}' 슬롯의 최저가 ({slot_size}곳 중)"


# ═══════════════════════════════════════════════════════════════
#  통계 — 검색 결과 인사이트
# ═══════════════════════════════════════════════════════════════
def build_stats(cards: list[dict], buckets: list[dict]) -> dict:
    """
    1. total / avg_price
    2. commute_curve  : 버킷별 평균가 + 매물수
    3. pyeong_breakdown : 평형별 평균가 + 매물수
    4. age_breakdown  : 신축(10년↓) / 준신축(20년↓) / 그 외 / 미상
    """
    total = len(cards)
    if not total:
        return {'total': 0}

    # 통근-가격 곡선
    commute_curve = []
    for b in buckets:
        bi = b['idx']
        in_bucket = [c for c in cards if c.get('bucket_idx') == bi]
        if in_bucket:
            avg = sum(c['price_low'] for c in in_bucket) / len(in_bucket)
            commute_curve.append({
                'label': b['label'],
                'avg_price': int(avg),
                'count': len(in_bucket),
            })

    # 평형별 평균
    by_pt: dict[str, list[int]] = {}
    for c in cards:
        by_pt.setdefault(c['pyeong_type'], []).append(c['price_low'])
    pyeong_breakdown = [
        {
            'pyeong_type': pt,
            'avg_price': int(sum(ps) / len(ps)),
            'count': len(ps),
        }
        for pt, ps in sorted(by_pt.items())
    ]

    # 연식 분포
    new_10, mid_20, old, unknown = 0, 0, 0, 0
    for c in cards:
        by = c.get('build_year')
        if not by:
            unknown += 1
            continue
        age = date.today().year - by
        if age <= 10:
            new_10 += 1
        elif age <= 20:
            mid_20 += 1
        else:
            old += 1

    return {
        'total': total,
        'avg_price': int(sum(c['price_low'] for c in cards) / total),
        'commute_curve': commute_curve,
        'pyeong_breakdown': pyeong_breakdown,
        'age_breakdown': {
            'new_10': new_10,
            'mid_20': mid_20,
            'old': old,
            'unknown': unknown,
        },
    }


# ═══════════════════════════════════════════════════════════════
#  LLM 친구 한 마디 — 추천 카드만 길게, 균형 잡힌 시각
# ═══════════════════════════════════════════════════════════════
def _fmt_price(manwon: int) -> str:
    if not manwon:
        return '-'
    e = manwon // 10000
    rem = (manwon % 10000) // 1000
    if rem == 0:
        return f'{e}억'
    return f'{e}억 {rem}천'


def _make_prompt_recommend(card: dict, avg_price_by_pt: dict, wp_label: str) -> str:
    """추천 카드용 — 균형잡힌 3~5문장, 단점 포함"""
    pt = card.get('pyeong_type', '')
    pl = card['price_low']
    price_str = _fmt_price(pl)

    # 동평균 대비
    avg_pt = avg_price_by_pt.get(pt, 0)
    vs_avg_str = ''
    if avg_pt > 0:
        vs_avg = round((pl / avg_pt - 1) * 100)
        sign = '+' if vs_avg > 0 else ''
        vs_avg_str = f'결과 내 {pt} 평균 대비 {sign}{vs_avg}%'

    # 연식
    by = card.get('build_year')
    age_str = ''
    if by:
        age = date.today().year - by
        age_str = f'{by}년 준공 ({age}년차)'

    # 통근
    transit_summary = card.get('transit_summary', '')
    bus = card.get('bus_cnt', 0) or 0
    sub = card.get('subway_cnt', 0) or 0
    transfer = max(bus + sub - 1, 0)
    transfer_str = '직통' if transfer == 0 else f'{transfer}회 환승'

    # 단지 정보
    top_floor = card.get('top_floor', '')
    kapt_cnt = card.get('kaptdaCnt', 0)
    deal_cnt = card.get('deal_count', 0)

    # 추천 슬롯 / 차액
    bl = card.get('bucket_label', '')
    diff = card.get('price_diff_vs_fastest', 0)
    diff_note = ''
    if diff > 0:
        diff_note = f'(같은 평형 최단권 최저가보다 {_fmt_price(diff)} 더 비쌈)'
    elif diff < 0:
        diff_note = f'(같은 평형 최단권 대비 {_fmt_price(abs(diff))} 저렴)'

    return f"""부동산 잘 아는 친구가 카톡으로 한마디 던지는 톤으로 평가해줘.

[규칙 - 엄격히 지킬 것]
- **2문장, 최대 80자.** 절대 그 이상 X.
- 카톡 톤. "~야", "~네", "~겠다" 자연스럽게.
- 보고서/평론가 표현 금지: "필요하고", "고려할 만하고", "검토해야", "감안하면" 등
- 장점 1개 + 단점 1개만 진짜 핵심으로 콕. 둘 다 수치 한 개씩만 인용.
- 이모지·따옴표 X. 한 문단으로.

[톤 예시]
- 좋음: "25분에 4억이면 진짜 싸. 근데 27년차 구축이라 인테리어 한 번은 해야 할 거야."
- 좋음: "2호선 직통이라 출퇴근 편하고 가격도 평균보다 싸. 세대수가 작아서 거래는 좀 한산할 듯."
- 나쁨 (이렇게 쓰지 마): "이 단지는 가격 경쟁력이 확실하지만 연식이 오래되어 리모델링 시점 확인이 필요하고..."

[단지 정보]
{card['apt_nm']} ({card['umd_nm']}, {kapt_cnt}세대, {age_str or '연식 미상'})
{pt} {price_str} ({vs_avg_str or '평균 비교 불가'}, 3년 거래 {deal_cnt}건)
{transit_summary} 총 {card['total_time_min']}분 ({transfer_str})

위 정보로 2문장 카톡:"""


async def _call_llm(prompt: str, model: str, max_tokens: int,
                    fallback_model: str | None = None) -> str:
    """LLM 호출. 실패 시 fallback_model로 재시도. 로그 출력."""
    client = _get_client()
    try:
        msg = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f'[LLM] {model} 실패: {type(e).__name__}: {e}')
        if fallback_model and fallback_model != model:
            print(f'[LLM] {fallback_model}로 폴백 시도')
            try:
                msg = await client.messages.create(
                    model=fallback_model,
                    max_tokens=max_tokens,
                    messages=[{'role': 'user', 'content': prompt}],
                )
                return msg.content[0].text.strip()
            except Exception as e2:
                print(f'[LLM] 폴백도 실패: {type(e2).__name__}: {e2}')
        return f'(생성 실패)'


# ── 일반 카드용 짧은 한마디 프롬프트 (Haiku) ────────────────
def _make_prompt_regular(card: dict, avg_price_by_pt: dict) -> str:
    pt = card.get('pyeong_type', '')
    pl = card['price_low']
    price_str = _fmt_price(pl)

    avg_pt = avg_price_by_pt.get(pt, 0)
    vs_avg_str = ''
    if avg_pt > 0:
        vs_avg = round((pl / avg_pt - 1) * 100)
        sign = '+' if vs_avg > 0 else ''
        vs_avg_str = f'동가격대 대비 {sign}{vs_avg}%'

    by = card.get('build_year')
    age_str = f'{date.today().year - by}년차' if by else ''

    transit_summary = card.get('transit_summary', '')
    bus = card.get('bus_cnt', 0) or 0
    sub = card.get('subway_cnt', 0) or 0
    transfer = max(bus + sub - 1, 0)
    transfer_str = '직통' if transfer == 0 else f'{transfer}회 환승'

    return f"""부동산 잘 아는 친구처럼 이 아파트 한 줄 평. 이모지 X, 반말, 40자 이내. 형식적 표현 반복 X.
{card['apt_nm']} ({card['umd_nm']}, {pt}{f', {age_str}' if age_str else ''}) | {transit_summary} {card['total_time_min']}분 {transfer_str} | {price_str} {vs_avg_str}
한 마디:"""


# ── 추천 카드용 긴 코멘트 (Sonnet, 균형잡힌 시각) ───────────
async def build_recommend_comments(
    recommended_cards: list[dict],
    all_cards: list[dict],
    wp_label: str,
) -> dict[str, dict]:
    """추천 카드 → Sonnet, 3~5문장 균형잡힌 코멘트 (장점+단점)"""
    if not recommended_cards:
        return {}

    by_pt: dict[str, list[int]] = {}
    for c in all_cards:
        by_pt.setdefault(c['pyeong_type'], []).append(c['price_low'])
    avg_price_by_pt = {pt: int(sum(ps) / len(ps)) for pt, ps in by_pt.items()}

    tasks, keys = [], []
    for c in recommended_cards:
        prompt = _make_prompt_recommend(c, avg_price_by_pt, wp_label)
        # Sonnet 실패 시 Haiku 폴백
        # 2문장 한도라 max_tokens는 작게. 폴백도 Haiku.
        tasks.append(_call_llm(prompt, SONNET_MODEL, max_tokens=150,
                               fallback_model=HAIKU_MODEL))
        keys.append(card_key(c))

    print(f'[LLM] 추천 코멘트 {len(tasks)}개 Sonnet 호출 시작')
    results = await asyncio.gather(*tasks, return_exceptions=True)
    print(f'[LLM] 추천 코멘트 {len(tasks)}개 완료')
    return {
        k: {'comment': r if isinstance(r, str) else '(생성 실패)', 'kind': 'recommend'}
        for k, r in zip(keys, results)
    }


# ── 일반 카드용 한 줄 평 (Haiku, 동시성 제한) ────────────────
async def build_regular_comments(
    regular_cards: list[dict],
    all_cards: list[dict],
    wp_label: str,
) -> dict[str, dict]:
    """일반 카드 전부 → Haiku 한 줄. 동시 8개 호출 제한 (rate limit 안전)"""
    if not regular_cards:
        return {}

    by_pt: dict[str, list[int]] = {}
    for c in all_cards:
        by_pt.setdefault(c['pyeong_type'], []).append(c['price_low'])
    avg_price_by_pt = {pt: int(sum(ps) / len(ps)) for pt, ps in by_pt.items()}

    sem = asyncio.Semaphore(REGULAR_CONCURRENCY)

    async def _bounded_call(c):
        async with sem:
            prompt = _make_prompt_regular(c, avg_price_by_pt)
            return await _call_llm(prompt, HAIKU_MODEL, max_tokens=80)

    tasks = [_bounded_call(c) for c in regular_cards]
    keys = [card_key(c) for c in regular_cards]
    print(f'[LLM] 일반 코멘트 {len(tasks)}개 Haiku 호출 시작 (동시 {REGULAR_CONCURRENCY})')
    results = await asyncio.gather(*tasks, return_exceptions=True)
    print(f'[LLM] 일반 코멘트 {len(tasks)}개 완료')
    return {
        k: {'comment': r if isinstance(r, str) else '(생성 실패)', 'kind': 'regular'}
        for k, r in zip(keys, results)
    }


# ── 통합 진입점 (호환성 유지) ────────────────────────────────
async def build_comments(
    target_cards: list[dict],
    all_cards: list[dict],
    wp_label: str,
) -> dict[str, dict]:
    """
    target_cards 안에 추천/일반 섞여 있으면 자동 분리해서
    Sonnet (추천) + Haiku (일반) 동시 호출.
    """
    rec = [c for c in target_cards if c.get('is_recommended')]
    reg = [c for c in target_cards if not c.get('is_recommended')]

    rec_task = build_recommend_comments(rec, all_cards, wp_label)
    reg_task = build_regular_comments(reg, all_cards, wp_label)
    rec_result, reg_result = await asyncio.gather(rec_task, reg_task)

    return {**rec_result, **reg_result}


# ═══════════════════════════════════════════════════════════════
#  Deprecated — 호환성 유지용 (구버전 호출 대비)
# ═══════════════════════════════════════════════════════════════
TIER_BEST = "BEST"
TIER_GOOD = "GOOD"
TIER_SOSO = "SOSO"
TIER_LAST = "LAST"


def assign_tiers(cards: list[dict]) -> list[dict]:
    """Deprecated. build_recommendations 사용 권장."""
    for c in cards:
        c['tier'] = TIER_LAST
    return cards
