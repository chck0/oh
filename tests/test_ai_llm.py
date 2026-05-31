"""
tests/test_ai_llm.py — app/ai.py LLM 호출 경로 mock 단위 테스트

Spec 10: ai.py L316~474 커버리지 확보
- _call_llm: 정상 응답, RateLimitError 재시도, APIConnectionError, 폴백, 전체 실패
- build_recommend_comments: 빈 입력, N개 카드, kind='recommend'
- build_regular_comments: 빈 입력, Semaphore 제한, kind='regular'
- build_comments: 추천/일반 혼합 자동 분리
"""
import asyncio
import pytest
import httpx
import anthropic
from anthropic.types import TextBlock
from unittest.mock import AsyncMock, MagicMock, patch

import app.ai as ai_mod
from app.ai import (
    _call_llm,
    build_recommend_comments,
    build_regular_comments,
    build_comments,
    card_key,
    SONNET_MODEL,
    HAIKU_MODEL,
)


# ── 헬퍼 ─────────────────────────────────────────────────────

def _text_block(text: str) -> TextBlock:
    return TextBlock(type='text', text=text)


def _mock_message(text: str):
    msg = MagicMock()
    msg.content = [_text_block(text)]
    return msg


def _make_rate_limit_error():
    req = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    resp = httpx.Response(429, request=req)
    return anthropic.RateLimitError(
        message='rate limit exceeded', response=resp, body={}
    )


def _make_conn_error():
    req = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    return anthropic.APIConnectionError(message='connection error', request=req)


def _card(apt_seq='APT001', pyeong_type='20평대', is_recommended=False):
    return {
        'apt_seq': apt_seq,
        'pyeong_type': pyeong_type,
        'apt_nm': '테스트아파트',
        'umd_nm': '역삼동',
        'price_low': 80000,
        'price_high': 90000,
        'total_time_min': 25,
        'bus_cnt': 0,
        'subway_cnt': 1,
        'transit_summary': '2호선 직통',
        'build_year': 2010,
        'deal_count': 5,
        'kaptdaCnt': 300,
        'top_floor': 15,
        'is_recommended': is_recommended,
    }


@pytest.fixture(autouse=True)
def reset_ai_client():
    """테스트마다 _client 전역 초기화."""
    ai_mod._client = None
    yield
    ai_mod._client = None


# ── _call_llm — 정상 케이스 ──────────────────────────────────

class TestCallLlmSuccess:
    @pytest.mark.asyncio
    async def test_returns_stripped_text(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_message('  테스트 코멘트  ')
        )
        with patch('app.ai._get_client', return_value=mock_client):
            result = await _call_llm('prompt', HAIKU_MODEL, 80)
        assert result == '테스트 코멘트'

    @pytest.mark.asyncio
    async def test_passes_model_and_max_tokens(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_message('ok')
        )
        with patch('app.ai._get_client', return_value=mock_client):
            await _call_llm('my prompt', SONNET_MODEL, 150)
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs['model'] == SONNET_MODEL
        assert call_kwargs.kwargs['max_tokens'] == 150

    @pytest.mark.asyncio
    async def test_non_text_block_returns_empty_string(self):
        """TextBlock이 아닌 블록 반환 시 빈 문자열 반환 — 500 에러 방지."""
        mock_block = MagicMock()  # spec 없음 → isinstance(block, TextBlock) = False
        mock_msg = MagicMock()
        mock_msg.content = [mock_block]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)
        with patch('app.ai._get_client', return_value=mock_client):
            result = await _call_llm('prompt', HAIKU_MODEL, 80)
        assert result == ''


# ── _call_llm — RateLimitError ────────────────────────────────

class TestCallLlmRateLimit:
    @pytest.mark.asyncio
    async def test_rate_limit_retries_and_succeeds(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[_make_rate_limit_error(), _mock_message('재시도 성공')]
        )
        with patch('app.ai._get_client', return_value=mock_client), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await _call_llm('prompt', HAIKU_MODEL, 80)
        assert result == '재시도 성공'
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_retry_fails_uses_fallback(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_rate_limit_error(),  # 첫 시도
                Exception('재시도도 실패'),  # 재시도
                _mock_message('폴백 성공'),  # fallback_model 호출
            ]
        )
        with patch('app.ai._get_client', return_value=mock_client), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await _call_llm('prompt', SONNET_MODEL, 150,
                                     fallback_model=HAIKU_MODEL)
        assert result == '폴백 성공'

    @pytest.mark.asyncio
    async def test_rate_limit_all_fail_returns_failure_string(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_rate_limit_error(),
                Exception('재시도 실패'),
                Exception('폴백도 실패'),
            ]
        )
        with patch('app.ai._get_client', return_value=mock_client), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await _call_llm('prompt', SONNET_MODEL, 150,
                                     fallback_model=HAIKU_MODEL)
        assert result == '(생성 실패)'


# ── _call_llm — 연결 오류 ─────────────────────────────────────

class TestCallLlmConnError:
    @pytest.mark.asyncio
    async def test_conn_error_retries_and_succeeds(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[_make_conn_error(), _mock_message('연결 재시도 성공')]
        )
        with patch('app.ai._get_client', return_value=mock_client), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            result = await _call_llm('prompt', HAIKU_MODEL, 80)
        assert result == '연결 재시도 성공'

    @pytest.mark.asyncio
    async def test_generic_exception_returns_failure(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception('알 수 없는 오류')
        )
        with patch('app.ai._get_client', return_value=mock_client):
            result = await _call_llm('prompt', HAIKU_MODEL, 80)
        assert result == '(생성 실패)'

    @pytest.mark.asyncio
    async def test_no_fallback_when_same_model(self):
        """fallback_model == model 이면 폴백 시도 안 함."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception('실패')
        )
        with patch('app.ai._get_client', return_value=mock_client):
            result = await _call_llm('prompt', HAIKU_MODEL, 80,
                                     fallback_model=HAIKU_MODEL)
        assert result == '(생성 실패)'
        assert mock_client.messages.create.call_count == 1


# ── build_recommend_comments ──────────────────────────────────

class TestBuildRecommendComments:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_dict(self):
        result = await build_recommend_comments([], [], 'wp')
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_recommend_kind(self):
        cards = [_card('APT001', '20평대', is_recommended=True)]
        with patch('app.ai._call_llm', new_callable=AsyncMock,
                   return_value='추천 코멘트'):
            result = await build_recommend_comments(cards, cards, '직장')
        key = card_key(cards[0])
        assert key in result
        assert result[key]['kind'] == 'recommend'
        assert result[key]['comment'] == '추천 코멘트'

    @pytest.mark.asyncio
    async def test_exception_becomes_failure_string(self):
        cards = [_card('APT001', '20평대', is_recommended=True)]
        with patch('app.ai._call_llm', new_callable=AsyncMock,
                   side_effect=Exception('LLM 오류')):
            result = await build_recommend_comments(cards, cards, '직장')
        key = card_key(cards[0])
        assert result[key]['comment'] == '(생성 실패)'

    @pytest.mark.asyncio
    async def test_multiple_cards_all_returned(self):
        cards = [
            _card('APT001', '20평대', True),
            _card('APT002', '30평대', True),
        ]
        with patch('app.ai._call_llm', new_callable=AsyncMock,
                   return_value='코멘트'):
            result = await build_recommend_comments(cards, cards, '직장')
        assert len(result) == 2


# ── build_regular_comments ────────────────────────────────────

class TestBuildRegularComments:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_dict(self):
        result = await build_regular_comments([], [], 'wp')
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_regular_kind(self):
        cards = [_card('APT001', '20평대', is_recommended=False)]
        with patch('app.ai._call_llm', new_callable=AsyncMock,
                   return_value='일반 코멘트'):
            result = await build_regular_comments(cards, cards, '직장')
        key = card_key(cards[0])
        assert result[key]['kind'] == 'regular'
        assert result[key]['comment'] == '일반 코멘트'

    @pytest.mark.asyncio
    async def test_multiple_cards(self):
        cards = [_card(f'APT{i:03d}', '20평대') for i in range(5)]
        with patch('app.ai._call_llm', new_callable=AsyncMock,
                   return_value='한 줄'):
            result = await build_regular_comments(cards, cards, '직장')
        assert len(result) == 5


# ── build_comments — 통합 ────────────────────────────────────

class TestBuildComments:
    @pytest.mark.asyncio
    async def test_splits_recommend_and_regular(self):
        rec_card = _card('APT001', '20평대', is_recommended=True)
        reg_card = _card('APT002', '30평대', is_recommended=False)
        cards = [rec_card, reg_card]

        with patch('app.ai._call_llm', new_callable=AsyncMock,
                   return_value='코멘트'):
            result = await build_comments(cards, cards, '직장')

        rec_key = card_key(rec_card)
        reg_key = card_key(reg_card)
        assert result[rec_key]['kind'] == 'recommend'
        assert result[reg_key]['kind'] == 'regular'

    @pytest.mark.asyncio
    async def test_all_regular_no_recommend_calls(self):
        cards = [_card('APT001', '20평대', is_recommended=False)]
        with patch('app.ai.build_recommend_comments',
                   new_callable=AsyncMock, return_value={}) as mock_rec, \
             patch('app.ai.build_regular_comments',
                   new_callable=AsyncMock,
                   return_value={card_key(cards[0]): {'comment': 'ok', 'kind': 'regular'}}):
            result = await build_comments(cards, cards, '직장')

        # recommend는 빈 카드 리스트로 호출됨
        rec_call_cards = mock_rec.call_args[0][0]
        assert rec_call_cards == []

    @pytest.mark.asyncio
    async def test_all_recommend_no_regular_calls(self):
        cards = [_card('APT001', '20평대', is_recommended=True)]
        with patch('app.ai.build_recommend_comments',
                   new_callable=AsyncMock,
                   return_value={card_key(cards[0]): {'comment': 'ok', 'kind': 'recommend'}}), \
             patch('app.ai.build_regular_comments',
                   new_callable=AsyncMock, return_value={}) as mock_reg:
            result = await build_comments(cards, cards, '직장')

        reg_call_cards = mock_reg.call_args[0][0]
        assert reg_call_cards == []

    @pytest.mark.asyncio
    async def test_results_merged(self):
        cards = [
            _card('APT001', '20평대', is_recommended=True),
            _card('APT002', '30평대', is_recommended=False),
        ]
        with patch('app.ai._call_llm', new_callable=AsyncMock,
                   return_value='코멘트'):
            result = await build_comments(cards, cards, '직장')
        assert len(result) == 2
