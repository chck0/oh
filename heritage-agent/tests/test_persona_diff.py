"""페르소나별 프롬프트 다양성 테스트 (Manifest #3 Hyper-Personalization).

같은 장소에 대해 어린이/일반/전문가 페르소나의 프롬프트가 확연히 달라야 한다.
"단어 몇 개만 다른 수준"이면 실패로 간주한다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.persona import build_prompt, get_voice_key


PLACE_NAME = "홍릉 정자각"
PLACE_LOCATION = "서울특별시"

REFERENCE_TEXT = (
    "홍릉 정자각은 대한제국 고종황제와 명성황후를 모신 홍릉의 제례 공간이다. "
    "1919년 고종 승하 후 조성되었으며, 황제릉 격식에 맞춰 기존 조선왕릉의 "
    "정자각보다 규모가 크고 장엄하게 설계되었다."
)

PERSONAS = {
    "child": {"name": "민준", "age": 8, "gender": "남성", "mbti": "ENFP", "expert_mode": False},
    "teen": {"name": "지혜", "age": 16, "gender": "여성", "mbti": "INFJ", "expert_mode": False},
    "adult": {"name": "수진", "age": 35, "gender": "여성", "mbti": "ISTJ", "expert_mode": False},
    "expert": {"name": "박교수", "age": 52, "gender": "남성", "mbti": "INTJ", "expert_mode": True},
}


def _jaccard(a, b):
    """두 문자열 간 단어 수준 자카드 유사도."""
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a and not set_b:
        return 1.0
    return len(set_a & set_b) / len(set_a | set_b)


def test_personas_are_distinct():
    """모든 페르소나 쌍의 유사도가 0.75 미만이어야 한다."""
    prompts = {
        key: build_prompt(profile, PLACE_NAME, PLACE_LOCATION, REFERENCE_TEXT)
        for key, profile in PERSONAS.items()
    }

    keys = list(prompts.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            sim = _jaccard(prompts[keys[i]], prompts[keys[j]])
            assert sim < 0.75, (
                f"FAIL: {keys[i]} vs {keys[j]} 유사도 {sim:.2f} "
                f"(≥ 0.75 → 단어 몇 개만 다른 수준)"
            )
            print(f"PASS: {keys[i]:<6} ↔ {keys[j]:<6} 유사도 {sim:.2f}")


def test_reference_text_is_injected():
    """reference_text가 프롬프트에 주입되어야 한다 (Manifest #1)."""
    prompt = build_prompt(
        PERSONAS["adult"], PLACE_NAME, PLACE_LOCATION, REFERENCE_TEXT
    )
    assert "[참고 자료]" in prompt, "참고 자료 헤더 누락"
    assert "홍릉 정자각은 대한제국" in prompt, "참고 텍스트 본문 누락"
    assert "절대 지어내지 마세요" in prompt, "할루시네이션 방어 문구 누락"
    print("PASS: 참고 자료 주입 확인")


def test_no_reference_safeguard():
    """reference_text가 없으면 [안전 지시]가 들어가야 한다 (Premortem #2)."""
    prompt = build_prompt(PERSONAS["adult"], PLACE_NAME, PLACE_LOCATION, None)
    assert "[안전 지시]" in prompt, "참고 자료 없을 때 안전 지시 누락"
    assert "공식 참고 자료가 없습니다" in prompt
    print("PASS: 참고 자료 없을 때 안전 지시 확인")


def test_travel_density_instruction():
    """몰랐을 정보 1개 이상 포함 지시 (Manifest #5)."""
    for key, profile in PERSONAS.items():
        prompt = build_prompt(profile, PLACE_NAME, PLACE_LOCATION, REFERENCE_TEXT)
        assert "몰랐을" in prompt, f"{key}: 여행 밀도 지시 누락"
    print("PASS: 모든 페르소나에 여행 밀도 지시 포함")


def test_voice_key_mapping():
    """페르소나별 TTS 음성 키 매핑."""
    assert get_voice_key(PERSONAS["child"]) == "child"
    assert get_voice_key(PERSONAS["teen"]) == "teenager"
    assert get_voice_key(PERSONAS["adult"]) == "adult_female"
    assert get_voice_key(PERSONAS["expert"]) == "expert"
    print("PASS: 페르소나별 음성 키 매핑 정상")


if __name__ == "__main__":
    test_personas_are_distinct()
    test_reference_text_is_injected()
    test_no_reference_safeguard()
    test_travel_density_instruction()
    test_voice_key_mapping()
    print("\n모든 페르소나 diff 테스트 통과 ✓")
