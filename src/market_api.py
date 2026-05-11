"""
market_api.py — FastAPI 백엔드 for VerifyHome 시세 AI 챗봇

실행:
    uvicorn src.market_api:app --reload --port 8000

프론트엔드에서 POST http://localhost:8000/api/chat 호출
"""

import os
from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

app = FastAPI(title="VerifyHome Market API")

# CORS — HTML 파일을 file:// 또는 다른 포트에서 열 때 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


# ── Request/Response 스키마 ──

class DongData(BaseModel):
    name: str
    data: list[float]

class ChartStats(BaseModel):
    complex_change_pct: float
    dong_change_pct: float
    complex_vs_dong_pct: float
    latest_complex: float
    latest_dong: float

class ChartContext(BaseModel):
    address: str = ""
    size_pyeong: int = 30
    months: list[str] = []
    complex: list[float] = []
    dong: list[float] = []
    active_dongs: list[DongData] = []
    stats: ChartStats | None = None

class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    context: ChartContext
    history: list[HistoryMessage] = []


class ChatResponse(BaseModel):
    reply: str


# ── Helpers ──

def build_context_str(ctx: ChartContext) -> str:
    """차트 데이터를 LLM 인풋 텍스트로 변환 (할루시네이션 방지)"""
    months_str = ", ".join(ctx.months) if ctx.months else "11월~4월"

    lines = [
        f"매물: {ctx.address} ({ctx.size_pyeong}평)",
        f"분석 기간: {months_str}",
        f"래미안아파트(단지) 평단가: {ctx.complex} (만원/평)",
        f"역삼동 평균 평단가: {ctx.dong} (만원/평)",
    ]

    if ctx.stats:
        s = ctx.stats
        lines += [
            f"단지 6개월 변화율: +{s.complex_change_pct}%",
            f"역삼동 평균 변화율: +{s.dong_change_pct}%",
            f"현재 단지 vs 동 평균: +{s.complex_vs_dong_pct}%",
            f"최신 단지 평단가: {s.latest_complex}만원/평",
            f"최신 역삼동 평균: {s.latest_dong}만원/평",
        ]

    if ctx.active_dongs:
        for d in ctx.active_dongs:
            pct = round((d.data[-1] / d.data[0] - 1) * 100, 1) if d.data[0] else 0
            lines.append(f"{d.name} 평단가: {d.data} (만원/평) / 6개월 변화: +{pct}%")

    return "\n".join(lines)


# ── Endpoint ──

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    context_str = build_context_str(req.context)

    system_prompt = f"""당신은 VerifyHome의 시세 분석 AI입니다.
사용자가 매입을 고려 중인 아파트의 실거래가 차트 데이터를 분석해 궁금증에 답합니다.

## 역할
- 차트 데이터를 쉽게 해석해 주는 동네 부동산 전문가처럼 말합니다.
- "데이터를 보면 ~" 식으로 근거를 명시합니다.
- 복잡한 수치를 일반인이 이해할 수 있는 언어로 풀어줍니다.

## 현재 분석 대상 (코드 계산값 — 이 수치만 사용)
{context_str}

## 답변 규칙
1. **할루시네이션 금지**: 위 계산값에 없는 수치는 절대 인용하지 않습니다.
   예) "강남 평균은 보통 ~" 같은 외부 일반 지식 X
2. **수치 근거 필수**: 모든 판단에 위 데이터의 숫자를 근거로 붙입니다.
   예) "단지가 +38%인데 역삼동 평균은 +34%이므로 4%p 아웃퍼폼했습니다."
3. **2~4문장**: 간결하게. 길게 나열하지 않습니다.
4. **투자 권유 금지**: "사세요/파세요" 금지. "데이터상으로는 ~로 보입니다" 수준까지만.
5. **비교 동이 추가된 경우**: 선택된 동 데이터를 적극 활용해 비교 분석합니다.
6. **한국어**로 답합니다.

## 자주 나오는 질문 유형별 가이드
- "비싼가요?" → 동 평균 대비 %, 6개월 변화율로 상대적 위치 설명
- "상승세 계속될까요?" → 데이터 추세만 서술, 예측은 하지 않음 ("6개월 연속 상승 중이나 향후는 알 수 없습니다")
- "어느 동이 더 싸요?" → 추가된 동 평단가 직접 비교
- "지금 사면 타이밍이 맞나요?" → 데이터 기반 현황만, 결론은 사용자에게 남김
"""

    # 대화 히스토리 구성 (Claude API 형식)
    messages: list[dict[str, Any]] = []
    for h in req.history[-10:]:  # 최근 10개만
        if h.role in ("user", "assistant"):
            messages.append({"role": h.role, "content": h.content})

    # 현재 메시지 추가
    messages.append({"role": "user", "content": req.message})

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system_prompt,
        messages=messages,
    )

    reply = response.content[0].text if response.content else "죄송합니다, 잠시 후 다시 시도해주세요."
    return ChatResponse(reply=reply)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
