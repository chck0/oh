"""페르소나별 프롬프트 관리 모듈 - 사용자 프로필 기반 동적 생성."""

# TTS 음성 매핑용
VOICE_MAP = {
    "child": "child",           # 12세 이하
    "teenager": "teenager",     # 13~18세
    "adult_male": "adult_male",
    "adult_female": "adult_female",
    "expert": "expert",         # 전문가 모드 (별도 체크)
}


def get_voice_key(profile):
    """프로필 정보로 TTS 음성 키를 결정한다."""
    if profile.get("expert_mode"):
        return "expert"

    age = profile.get("age", 25)
    gender = profile.get("gender", "남성")

    if age <= 12:
        return "child"
    elif age <= 18:
        return "teenager"
    elif gender == "남성":
        return "adult_male"
    else:
        return "adult_female"


def build_prompt(profile, place_name, place_location=""):
    """사용자 프로필 정보를 기반으로 Gemini 프롬프트를 생성한다.

    Args:
        profile: {"name": str, "age": int, "gender": str, "mbti": str, "expert_mode": bool}
        place_name: 인식된 건물/장소 이름
        place_location: 위치 정보 (도시, 국가)

    Returns:
        완성된 프롬프트 문자열
    """
    name = profile.get("name", "사용자")
    age = profile.get("age", 25)
    gender = profile.get("gender", "남성")
    mbti = profile.get("mbti", "")
    expert_mode = profile.get("expert_mode", False)

    # 나이대별 기본 톤
    if age <= 12:
        age_instruction = (
            f"{name}은(는) {age}살 어린이야.\n"
            "아이가 이해할 수 있는 쉬운 말로 설명해줘.\n"
            "재미있는 비유와 예시를 많이 써줘. \"레고\", \"게임\", \"만화\" 같은 것에 비유해도 좋아.\n"
            "3~4문장 정도로 짧게 설명해줘.\n"
            "어려운 전문 용어는 쓰지 마."
        )
    elif age <= 18:
        age_instruction = (
            f"{name}은(는) {age}살 학생이야.\n"
            "교과서에 나오는 내용과 연결해서 설명해줘.\n"
            "건물과 관련된 인물들의 드라마 같은 이야기를 중심으로 흥미롭게 풀어줘.\n"
            "\"~했다고 해요\", \"~인 거죠\" 같은 친근한 말투를 사용해.\n"
            "4~6문장 정도로 설명해줘."
        )
    else:
        age_instruction = (
            f"{name}은(는) {age}살 성인이야.\n"
            "교양 있고 흥미로운 톤으로 설명해줘.\n"
            "역사적 맥락, 건축 양식, 관련 인물을 자연스럽게 풀어줘.\n"
            "5~7문장 정도로 설명해줘."
        )

    # 전문가 모드 오버라이드
    if expert_mode:
        age_instruction = (
            f"{name}은(는) 전문가 수준의 깊이 있는 설명을 원해.\n"
            "학술 용어를 사용해도 되고, 건축 양식과 역사적 맥락을 상세히 분석해줘.\n"
            "설계자, 건축 시기, 양식을 정확히 분석하고 학계의 다양한 해석도 소개해줘.\n"
            "7~10문장 정도로 심층적으로 설명해줘."
        )

    # 성별에 따른 관점 힌트
    if not expert_mode:
        if gender == "남성":
            gender_hint = "건축 구조, 공법, 설계 철학 등 기술적 관점을 적절히 포함해줘."
        elif gender == "여성":
            gender_hint = "예술적 아름다움, 그 속에 담긴 사람들의 이야기를 적절히 포함해줘."
        else:
            gender_hint = ""
    else:
        gender_hint = ""

    # MBTI에 따른 스타일 힌트
    mbti_hint = ""
    if mbti:
        mbti_upper = mbti.upper()
        if mbti_upper[0:1] == "E":
            mbti_hint += "활기차고 대화하듯 설명해줘. "
        elif mbti_upper[0:1] == "I":
            mbti_hint += "차분하고 깊이 있게 설명해줘. "

        if "N" in mbti_upper:
            mbti_hint += "상상력을 자극하는 비유와 큰 그림을 그려줘. "
        elif "S" in mbti_upper:
            mbti_hint += "구체적인 사실과 디테일 중심으로 설명해줘. "

        if "F" in mbti_upper:
            mbti_hint += "감정적으로 공감할 수 있는 이야기를 포함해줘. "
        elif "T" in mbti_upper:
            mbti_hint += "논리적이고 분석적인 관점으로 설명해줘. "

        if mbti_upper[-1:] == "P":
            mbti_hint += "자유롭고 열린 톤으로 이야기해줘."
        elif mbti_upper[-1:] == "J":
            mbti_hint += "체계적이고 정리된 형식으로 설명해줘."

    # 프롬프트 조합
    location_info = f" ({place_location})" if place_location else ""

    parts = [
        f"너는 맞춤형 건축/문화재 가이드야.",
        age_instruction,
    ]
    if gender_hint:
        parts.append(gender_hint)
    if mbti_hint:
        parts.append(f"\n이 사용자의 MBTI는 {mbti}이야. {mbti_hint}")

    parts.extend([
        f"\n사용자가 보고 있는 장소: {place_name}{location_info}",
        f"\n사용자가 업로드한 사진에 보이는 건물/장소에 대해 설명해주세요.",
        "건물의 역사, 건축 양식, 의미, 관련 인물 등을 포함해서 설명해줘.",
        "한국어로 답변해줘.",
    ])

    return "\n".join(parts)
