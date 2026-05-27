"""tests/test_ai_multiblock.py
Claude multi-block 응답 안전 파싱 시뮬레이션 테스트

검증 목표:
    app/ai.py _call_llm이 ThinkingBlock / ToolUseBlock 등 비텍스트 블록이
    포함된 응답에서 AttributeError 없이 TextBlock만 추출하는지 확인한다.
    (이전 코드: msg.content[0].text 직접 접근 → 500 에러 유발)
"""
import asyncio
import sys
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anthropic

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import app.ai as ai_module  # noqa: E402


# ── 블록 팩토리 ───────────────────────────────────────────────────────
def _text(text: str) -> anthropic.types.TextBlock:
    """실제 TextBlock 인스턴스 — isinstance(b, anthropic.types.TextBlock) True."""
    return anthropic.types.TextBlock(type="text", text=text)


class _FakeThinkingBlock:
    """ThinkingBlock 시뮬레이션 — .text 속성 없음."""
    type = "thinking"
    thinking = "I'm reasoning step by step..."


class _FakeToolUseBlock:
    """ToolUseBlock 시뮬레이션 — .text 속성 없음."""
    type = "tool_use"
    name = "search"
    input: dict = {}


def _response(*blocks):
    """Mock Message 응답 생성."""
    resp = MagicMock()
    resp.content = list(blocks)
    return resp


# ── 픽스처 ───────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def reset_ai_client():
    """테스트 간 전역 클라이언트 격리."""
    ai_module._client = None
    yield
    ai_module._client = None


# ── 헬퍼 ─────────────────────────────────────────────────────────────
def _mock_client(*responses):
    """side_effect 리스트로 AsyncMock 클라이언트 생성."""
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=list(responses))
    return client


def _run(coro):
    return asyncio.run(coro)


# ── 테스트 ───────────────────────────────────────────────────────────
class TestCallLLMMultiBlock:
    """_call_llm multi-block 안전 파싱 시뮬레이션."""

    def test_text_only_returns_text(self):
        """TextBlock만 있을 때 정상 추출."""
        client = _mock_client(_response(_text("안녕하세요")))
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(ai_module._call_llm("prompt", "model", 100))
        assert result == "안녕하세요"

    def test_thinking_before_text_no_error(self):
        """ThinkingBlock + TextBlock — AttributeError 없이 TextBlock만 추출."""
        client = _mock_client(_response(_FakeThinkingBlock(), _text("결론입니다")))
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(ai_module._call_llm("prompt", "model", 100))
        assert result == "결론입니다"

    def test_tool_use_before_text_no_error(self):
        """ToolUseBlock + TextBlock — AttributeError 없이 TextBlock만 추출."""
        client = _mock_client(_response(_FakeToolUseBlock(), _text("도구 후 텍스트")))
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(ai_module._call_llm("prompt", "model", 100))
        assert result == "도구 후 텍스트"

    def test_multiple_non_text_blocks_before_text(self):
        """Thinking + ToolUse + Text 순서 — TextBlock만 추출."""
        client = _mock_client(_response(
            _FakeThinkingBlock(),
            _FakeToolUseBlock(),
            _text("최종 답변"),
        ))
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(ai_module._call_llm("prompt", "model", 100))
        assert result == "최종 답변"

    def test_no_text_block_returns_empty_string(self):
        """TextBlock 없을 때 빈 문자열 반환 — 500 에러 방지."""
        client = _mock_client(_response(_FakeThinkingBlock(), _FakeToolUseBlock()))
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(ai_module._call_llm("prompt", "model", 100))
        assert result == ""

    def test_fallback_also_handles_mixed_blocks(self):
        """주 모델 실패 → 폴백 모델도 ThinkingBlock 포함 응답 안전 처리."""
        client = _mock_client(
            Exception("primary model failed"),
            _response(_FakeThinkingBlock(), _text("폴백 결과")),
        )
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(
                ai_module._call_llm("prompt", "model-a", 100, fallback_model="model-b")
            )
        assert result == "폴백 결과"

    def test_both_models_fail_returns_failure_string(self):
        """주 + 폴백 모두 실패 시 실패 메시지 반환 (예외 미전파)."""
        client = _mock_client(
            Exception("primary failed"),
            Exception("fallback failed"),
        )
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(
                ai_module._call_llm("prompt", "model-a", 100, fallback_model="model-b")
            )
        assert "실패" in result

    def test_whitespace_stripped(self):
        """TextBlock 텍스트 앞뒤 공백 제거 확인."""
        client = _mock_client(_response(_text("  공백 포함 텍스트  ")))
        with patch.object(ai_module, '_get_client', return_value=client):
            result = _run(ai_module._call_llm("prompt", "model", 100))
        assert result == "공백 포함 텍스트"
