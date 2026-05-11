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

    system_prompt = f"""당신은 부동산 시세 분석 AI 어시스턴트입니다.
아래 차트 데이터를 바탕으로 사용자의 질문에 간결하고 정확하게 답하세요.

[차트 데이터 — 계산값]
{context_str}

[규칙]
- 제공된 수치만 사용하세요. 외부 데이터나 일반 시장 추정을 인용하지 마세요.
- 수치 근거를 명시하세요 (예: "단지 6개월 +38%이므로...").
- 답변은 2~4문장으로 간결하게 하세요.
- 한국어로 답하세요.
- 투자 권유나 확정적 예측은 하지 마세요. 데이터 기반 해석만 제공하세요.
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
