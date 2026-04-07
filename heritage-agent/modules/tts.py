"""텍스트 → 음성 변환 모듈 - 페르소나별 목소리 적용."""

import asyncio
import re
from io import BytesIO


def _clean_markdown(text):
    """마크다운 기호를 제거하여 TTS가 자연스럽게 읽도록 한다."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"[`~]", "", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


# 페르소나별 음성 설정 (안정적인 기본 음성 사용)
PERSONA_VOICE = {
    "child": {
        "voice": "ko-KR-SunHiNeural",
        "rate": "+15%",
        "pitch": "+10Hz",
    },
    "teenager": {
        "voice": "ko-KR-SunHiNeural",
        "rate": "+10%",
        "pitch": "+0Hz",
    },
    "adult_male": {
        "voice": "ko-KR-InJoonNeural",
        "rate": "+5%",
        "pitch": "+0Hz",
    },
    "adult_female": {
        "voice": "ko-KR-SunHiNeural",
        "rate": "+5%",
        "pitch": "+0Hz",
    },
    "expert": {
        "voice": "ko-KR-InJoonNeural",
        "rate": "+0%",
        "pitch": "-5Hz",
    },
}

DEFAULT_VOICE = PERSONA_VOICE["adult_male"]

# 모든 fallback 시도 순서
FALLBACK_VOICES = ["ko-KR-SunHiNeural", "ko-KR-InJoonNeural"]


async def _generate_speech(text, voice, rate, pitch):
    """edge-tts로 음성을 생성한다."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    mp3_buffer = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_buffer.write(chunk["data"])
    mp3_buffer.seek(0)
    return mp3_buffer


def _run_async(coro):
    """비동기 함수를 실행한다. Streamlit 환경 대응."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _tts_with_gtts(text):
    """gTTS로 음성을 생성한다 (fallback)."""
    from gtts import gTTS
    tts = gTTS(text=text, lang="ko")
    mp3_buffer = BytesIO()
    tts.write_to_fp(mp3_buffer)
    mp3_buffer.seek(0)
    return mp3_buffer


def text_to_speech(text, persona="adult_male"):
    """텍스트를 페르소나에 맞는 음성(mp3)으로 변환한다."""
    config = PERSONA_VOICE.get(persona, DEFAULT_VOICE)
    text = _clean_markdown(text)

    if not text:
        text = "설명을 생성할 수 없었습니다."

    # 1차: 페르소나 음성 시도
    try:
        return _run_async(
            _generate_speech(text, config["voice"], config["rate"], config["pitch"])
        )
    except Exception:
        pass

    # 2차: fallback 음성 시도 (기본 설정)
    for voice in FALLBACK_VOICES:
        try:
            return _run_async(
                _generate_speech(text, voice, "+0%", "+0Hz")
            )
        except Exception:
            continue

    # 3차: gTTS fallback
    try:
        return _tts_with_gtts(text)
    except Exception:
        # 최종 실패 시 빈 오디오 반환
        return BytesIO(b"")
