"""
단지 친구 채팅 라우터 (spec-22 ~ spec-27)

POST /api/apt/{apt_seq}/chat : Claude Opus 기반 아파트 Q&A
  - 시세 통계 / 변동 / 동평균 / 실거래 / POI를 시스템 프롬프트로 주입
  - search_web tool (DuckDuckGo) agentic loop
  - 첨부 파일(이미지/PDF/텍스트) 처리

search.py에서 router.include_router(chat_router)로 합쳐진다.
search 모듈을 import하지 않으므로 순환 의존 없음.
"""
import hashlib
import json
import re
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db import get_db
from config import cfg

router = APIRouter()


# ── 채팅 인메모리 캐시 (spec-23) ────────────────────────────────
_chat_cache: dict = {}


def _chat_cache_get(key: tuple) -> "str | None":
    item = _chat_cache.get(key)
    if item and (time.time() - item[0]) < cfg.CHAT_CACHE_TTL_S:
        return item[1]
    return None


def _chat_cache_set(key: tuple, reply: str) -> None:
    now = time.time()
    expired = [k for k, v in _chat_cache.items() if now - v[0] >= cfg.CHAT_CACHE_TTL_S]
    for k in expired:
        del _chat_cache[k]
    _chat_cache[key] = (now, reply)


def _do_search(query: str) -> str:
    """DuckDuckGo Instant Answer API — API 키 불필요 (spec-24 F3)."""
    import urllib.request
    import urllib.parse
    import json as _json
    try:
        q = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "badugi-chat/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        abstract   = data.get("AbstractText", "").strip()
        source_url  = data.get("AbstractURL", "").strip()
        source_name = data.get("AbstractSource", "").strip()
        related = [
            t.get("Text", "")
            for t in data.get("RelatedTopics", [])[:3]
            if isinstance(t, dict) and t.get("Text")
        ]
        result = abstract or "\n".join(related)
        if result and source_url:
            label = source_name or source_url
            result += f"\n[출처: {label}] {source_url}"
        return result or "관련 공식 정보를 찾지 못했어."
    except Exception as e:
        return f"검색 오류: {type(e).__name__}"


def _extract_doc_text(data: bytes, media_type: str, filename: str) -> str:
    """PDF / 텍스트 → 최대 3000자 텍스트 추출 (spec-27).
    Word/PPT는 lxml 의존으로 Vercel 미지원 → 안내 메시지 반환."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext in ("docx", "pptx") or "wordprocessingml" in media_type or "presentationml" in media_type:
            return f"[{filename} 파일은 PDF로 변환 후 첨부해주세요]"
        if ext == "pdf" or media_type == "application/pdf":
            from pypdf import PdfReader
            import io as _io
            reader = PdfReader(_io.BytesIO(data))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages[:10]
            ).strip()[:3000]
        if ext == "txt" or media_type.startswith("text/"):
            return data.decode("utf-8", errors="ignore")[:3000]
    except Exception as e:
        return f"[파일 파싱 오류: {type(e).__name__}]"
    return ""


def _parse_reply(raw: str) -> "tuple[str, list[str]]":
    """CHIPS 줄을 분리해 (reply, suggestions) 반환."""
    chips_match = re.search(r"\nCHIPS:\s*(.+)$", raw, re.MULTILINE)
    if not chips_match:
        return raw.strip(), []
    suggestions = [s.strip() for s in chips_match.group(1).split("|")][:3]
    suggestions = [s for s in suggestions if s]
    return raw[: chips_match.start()].strip(), suggestions


# ── SSE (스트리밍) 헬퍼 ────────────────────────────────────────
_CHIPS_MARK = "\nCHIPS:"

_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",      # nginx/프록시 버퍼링 방지
    "Connection": "keep-alive",
}


def _sse(obj: dict) -> str:
    """dict → SSE data 프레임."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ── POST /api/apt/{apt_seq}/chat  (spec-22: 친구 채팅) ─────────
class AptChatRequest(BaseModel):
    pyeong_type: str | None = None
    wp_id:       int | None = None
    message:     str = Field(default="", max_length=500)
    history:     list[dict] = Field(default_factory=list)
    attachments: list[dict] | None = Field(default=None)  # spec-27: [{type, media_type, data, filename}]


_SEARCH_TOOLS = [
    {
        "name": "search_web",
        "description": "학군·지역정보·개발계획·최신뉴스 등 실시간 정보 검색 (DuckDuckGo)",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색어 (한국어 포함 가능)"}
            },
            "required": ["query"],
        },
    }
]


@router.post("/apt/{apt_seq}/chat")
def apt_chat(apt_seq: str, req: AptChatRequest, conn=Depends(get_db)):
    import anthropic as _anth
    import datetime as _dt

    apt = conn.execute(
        "SELECT apt_nm, umd_nm, kaptdaCnt, build_year FROM apartments WHERE apt_seq=? LIMIT 1",
        [apt_seq],
    ).fetchone()
    if not apt:
        raise HTTPException(status_code=404, detail="단지를 찾을 수 없어요")

    history_len = len(req.history or [])
    has_attachment = bool(req.attachments)
    cache_key = (apt_seq, hashlib.md5(req.message.encode()).hexdigest(), history_len)
    if not has_attachment and history_len <= 2:
        cached = _chat_cache_get(cache_key)
        if cached:
            reply, suggestions = _parse_reply(cached)

            def _cached_gen():
                if reply:
                    yield _sse({'type': 'delta', 'text': reply})
                yield _sse({'type': 'done', 'suggestions': suggestions})

            return StreamingResponse(
                _cached_gen(), media_type='text/event-stream', headers=_SSE_HEADERS)

    def _fmt(v: int) -> str:
        e, m = v // 10000, v % 10000
        return f"{e}억{f' {m:,}만' if m else ''}"

    today = _dt.date.today()
    threshold_year = today.year - 1
    d6 = today - _dt.timedelta(days=183)
    d3 = today - _dt.timedelta(days=91)

    stat_rows = conn.execute("""
        SELECT pyeong_type, pyeong,
               ROUND(AVG(deal_amount_int)) AS avg_amt,
               MIN(deal_amount_int) AS min_amt,
               MAX(deal_amount_int) AS max_amt,
               COUNT(*) AS cnt
        FROM trade_history
        WHERE apt_seq = ? AND deal_year >= ?
        GROUP BY pyeong_type, pyeong
        ORDER BY cnt DESC
    """, [apt_seq, threshold_year]).fetchall()

    trend_rows = conn.execute("""
        SELECT deal_year, deal_month, pyeong_type,
               ROUND(AVG(deal_amount_int)) AS avg_amt
        FROM trade_history
        WHERE apt_seq = ?
          AND (deal_year > ? OR (deal_year = ? AND deal_month >= ?))
        GROUP BY deal_year, deal_month, pyeong_type
        ORDER BY pyeong_type, deal_year, deal_month
    """, [apt_seq, d6.year, d6.year, d6.month]).fetchall()

    dong_avg_rows = conn.execute("""
        SELECT pyeong_type, ROUND(AVG(deal_amount_int)) AS avg_amt
        FROM trade_history
        WHERE umd_nm = ?
          AND (deal_year > ? OR (deal_year = ? AND deal_month >= ?))
        GROUP BY pyeong_type
    """, [apt['umd_nm'], d6.year, d6.year, d6.month]).fetchall()

    trades = conn.execute(
        "SELECT pyeong_type, pyeong, deal_year, deal_month, deal_day, deal_amount_int, floor "
        "FROM trade_history WHERE apt_seq=? "
        "ORDER BY deal_year DESC, deal_month DESC, deal_day DESC LIMIT 20",
        [apt_seq],
    ).fetchall()

    stat_lines = [
        f"- {r['pyeong_type']}({r['pyeong']:.0f}평): "
        f"평균 {_fmt(int(r['avg_amt']))} / "
        f"최저 {_fmt(int(r['min_amt']))} / "
        f"최고 {_fmt(int(r['max_amt']))} / "
        f"거래 {r['cnt']}건"
        for r in stat_rows
    ]

    trend_by_type: dict = {}
    for r in trend_rows:
        pt = r['pyeong_type']
        ym = (r['deal_year'], r['deal_month'])
        trend_by_type.setdefault(pt, {})[ym] = int(r['avg_amt'])

    change_lines = []
    for pt, monthly in trend_by_type.items():
        recent = [v for (y, m), v in monthly.items()
                  if y > d3.year or (y == d3.year and m >= d3.month)]
        prev = [v for (y, m), v in monthly.items()
                if not (y > d3.year or (y == d3.year and m >= d3.month))]
        if recent and prev:
            chg = round((sum(recent) / len(recent) - sum(prev) / len(prev))
                        / (sum(prev) / len(prev)) * 100, 1)
            sign = '+' if chg > 0 else ''
            change_lines.append(f"- {pt}: {sign}{chg}%")

    dong_lines = [
        f"- {apt['umd_nm']} {r['pyeong_type']}: 평균 {_fmt(int(r['avg_amt']))}"
        for r in dong_avg_rows
    ]

    trade_lines = "\n".join(
        f"- {r['pyeong_type']}({r['pyeong']:.0f}평) "
        f"{r['deal_year']}.{r['deal_month']:02d}.{r['deal_day']:02d} "
        f"{_fmt(r['deal_amount_int'])} {r['floor']}층"
        for r in trades
    ) or "실거래 데이터 없음"

    # 도보 주요 시설 (10분 이내)
    poi_rows = conn.execute("""
        SELECT poi_lclas_cd, poi_nm, walking_min
        FROM apt_walking_poi
        WHERE kaptCode = (
            SELECT kaptCode FROM apartments WHERE apt_seq = ? LIMIT 1
        )
          AND walking_min <= ?
        ORDER BY walking_min, poi_lclas_cd
        LIMIT 20
    """, [apt_seq, cfg.POI_WALK_MAX_MIN]).fetchall()
    poi_lines = [
        f"- {r['poi_nm']} ({r['poi_lclas_cd']}, 도보 {r['walking_min']}분)"
        for r in poi_rows
    ]

    system = f"""너는 부동산을 잘 아는 친한 친구야. 아래 아파트 정보를 바탕으로 친구처럼 솔직하게 답해줘.
반말, 카톡 말투. 5줄 이내.
모르는 건 search_web 도구로 검색해서 답해. 검색 결과가 없거나 제한적이면 "공식 확인이 필요해" 라고 표현해 ("검색이 잘 안 나와" 같은 말은 절대 쓰지 마).
실시간 호가·전세 정보는 없으니 추정할 때 반드시 "확인 필요"를 붙여.
교통 호재·재개발·정부 정책을 언급할 땐 반드시 출처를 명시해. 예: [출처: 기사제목 또는 URL]

답변 마지막에 공백 한 줄 후 반드시 이 형식으로 한국어 후속 질문 3개를 추가해:
CHIPS: 질문1 | 질문2 | 질문3

[후속 질문 칩(CHIPS) 생성 규칙 — 엄수]
- 100% 팩트 기반: 공공데이터·아파트 관리규약·네이버부동산 등에서 객관적으로 확인 가능한
  정보(숫자·명칭·거리·세대수·준공년도·실거래가·도보시간 등)만 질문으로 만든다.
- 카테고리 다변화: 방금 답한 주제에 이어 사용자가 다른 정보도 볼 수 있도록
  [교통]·[학군/교육]·[단지/시설]·[주변환경]·[시세/실거래] 중 서로 다른 카테고리로 3개를 균형 있게 고른다.
- 매번 새로운 각도로: 직전 대화에서 이미 다뤘거나 비슷한 질문은 피하고, 매 응답마다
  다른 시설명·지표·평형 등 구체적인 대상을 바꿔가며 신선한 질문을 만든다.
- 아래에 해당하거나 비슷한 뉘앙스의 질문은 절대 생성하지 마라(발견 즉시 제외):
  · 미래 가치·가격 예측 ("앞으로 집값 오를까?", "재건축 분담금 얼마쯤?" 등)
  · 주관적 호재/악재 평가 ("가장 큰 호재는?", "개발 호재 추천" 등)
    — 단, 확정·착공된 지하철역 거리 같은 객관 사실은 [교통] 카테고리로 허용
  · 투자·매수 권유 ("갭투자 타이밍?", "실거주로 추천해?" 등)
  · 입증 안 된 커뮤니티성 소문 ("층간소음 심해?", "주민 민도 어때?" 등)

== 단지 ==
{apt['apt_nm']} · {apt['umd_nm']} · {(apt['kaptdaCnt'] or 0):,}세대 · 준공 {apt['build_year'] or '미상'}년

== 시세 통계 (1년 기준) ==
{chr(10).join(stat_lines) or '데이터 없음'}

== 6개월 시세 변동 ==
{chr(10).join(change_lines) or '데이터 부족'}

== 동 평균 시세 (최근 6개월) ==
{chr(10).join(dong_lines) or '데이터 없음'}

== 최근 실거래 (최대 20건) ==
{trade_lines}

== 도보 10분 이내 주요 시설 ==
{chr(10).join(poi_lines) or '시설 데이터 없음'}"""

    # spec-27: 첨부 파일 처리
    import base64 as _b64
    image_blocks: list[dict] = []
    doc_texts: list[str] = []
    for att in (req.attachments or [])[:1]:  # 최대 1개
        att_data = att.get("data", "")
        if not att_data:
            continue
        att_bytes = _b64.b64decode(att_data)
        att_type = att.get("type", "")
        att_media = att.get("media_type", "")
        att_fname = att.get("filename", "파일")
        if att_type == "image":
            image_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": att_media, "data": att_data},
            })
        else:
            text = _extract_doc_text(att_bytes, att_media, att_fname)
            if text:
                doc_texts.append(f"== 첨부 파일 ({att_fname}) ==\n{text}")

    # 문서 텍스트를 시스템 프롬프트에 추가
    if doc_texts:
        system += "\n\n" + "\n\n".join(doc_texts)

    messages: list[dict] = []
    for h in (req.history or []):
        if h.get('role') in ('user', 'assistant') and h.get('content'):
            messages.append({'role': h['role'], 'content': str(h['content'])})

    # 이미지 첨부 시 vision content blocks
    user_text = req.message or "이 파일을 분석해줘."
    if image_blocks:
        messages.append({'role': 'user', 'content': image_blocks + [{"type": "text", "text": user_text}]})
    else:
        messages.append({'role': 'user', 'content': user_text})

    def _gen():
        """SSE 스트림 — 토큰을 받는 대로 흘려보낸다.

        - delta : 화면에 즉시 누적할 텍스트 조각
        - done  : 종료 + 후속질문(chips)
        - error : 오류 메시지
        CHIPS: 마커 이후는 화면에 흘리지 않고 done의 suggestions로 분리한다.
        """
        full = ''       # 모델이 생성한 누적 원문(프리앰블+답변)
        emitted = 0     # 이미 delta로 내보낸 길이
        suggestions: list[str] = []
        try:
            client = _anth.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

            # F3: tool_use agentic loop (최대 3턴) — 각 턴을 스트리밍
            MAX_TOOL_TURNS = 3
            final_msg = None
            for _ in range(MAX_TOOL_TURNS + 1):
                with client.messages.stream(
                    model=cfg.OPUS_MODEL,
                    max_tokens=700,
                    system=system,
                    messages=messages,
                    tools=_SEARCH_TOOLS,
                ) as stream:
                    for delta in stream.text_stream:
                        full += delta
                        idx = full.find(_CHIPS_MARK)
                        # CHIPS 마커가 보이면 그 앞까지만, 아니면 마커 길이만큼 홀드백
                        safe = idx if idx != -1 else max(emitted, len(full) - len(_CHIPS_MARK))
                        if safe > emitted:
                            yield _sse({'type': 'delta', 'text': full[emitted:safe]})
                            emitted = safe
                    final_msg = stream.get_final_message()

                if final_msg.stop_reason != 'tool_use':
                    break
                # 검색 도구 실행 후 다음 턴 진행
                messages.append({'role': 'assistant', 'content': final_msg.content})
                tool_results = []
                for block in final_msg.content:
                    if block.type == 'tool_use':
                        search_result = _do_search(block.input.get('query', ''))
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': search_result,
                        })
                messages.append({'role': 'user', 'content': tool_results})

            # 종료 — CHIPS 분리 + 잔여 텍스트 flush
            idx = full.find(_CHIPS_MARK)
            if idx != -1:
                reply_text = full[:idx]
                m = re.search(r'CHIPS:\s*(.+)', full[idx:])
                if m:
                    suggestions = [s.strip() for s in m.group(1).split('|') if s.strip()][:3]
            else:
                reply_text = full
            if len(reply_text) > emitted:
                yield _sse({'type': 'delta', 'text': reply_text[emitted:]})

            if not has_attachment and history_len <= 2 and full.strip():
                _chat_cache_set(cache_key, full)

            yield _sse({'type': 'done', 'suggestions': suggestions})
        except Exception as e:
            yield _sse({'type': 'error',
                        'message': f'에러가 났어. 잠깐 기다려봐. ({type(e).__name__})'})

    return StreamingResponse(_gen(), media_type='text/event-stream', headers=_SSE_HEADERS)
