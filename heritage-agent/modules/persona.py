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


def build_prompt(profile, place_name, place_location="", reference_text=None):
    """사용자 프로필 정보를 기반으로 Gemini 프롬프트를 생성한다.

    Manifest #1 'Data Integrity' 구현: reference_text가 주어지면 공인 자료 기반으로
    답변하도록 지시하고, 없으면 확신 없는 내용은 솔직하게 밝히도록 안전장치를 건다.

    Args:
        profile: {"name": str, "age": int, "gender": str, "mbti": str, "expert_mode": bool}
        place_name: 인식된 건물/장소 이름
        place_location: 위치 정보 (도시, 국가)
        reference_text: 로컬 발굴/관리 보고서 발췌 (있으면 프롬프트에 주입)

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
    ])

    # ── Data Integrity: 참고 자료 주입 (Manifest #1, Premortem #1) ──
    if reference_text:
        parts.append(
            "\n[참고 자료]\n"
            "아래는 이 장소에 대한 공식 발굴/관리 보고서 발췌입니다. "
            "이 자료에 근거해서 설명해주세요. "
            "자료에 명시되지 않은 세부 사실(건립 연도, 인물 일화, 양식 등)은 "
            "절대 지어내지 마세요.\n"
            "---\n"
            f"{reference_text}\n"
            "---"
        )
    else:
        parts.append(
            "\n[안전 지시]\n"
            "이 장소에 대한 공식 참고 자료가 없습니다. "
            "확실하지 않은 세부 사실(정확한 건립 연도, 설계자, 인물 일화)은 "
            "'~라고 알려져 있어요' 또는 '전해지는 이야기에 따르면'으로 표현해주세요. "
            "모르는 부분은 '이 부분은 자료가 부족해서 정확히 말씀드리기 어려워요'라고 "
            "솔직하게 밝혀주세요."
        )

    # 여행의 밀도 (Manifest #5): "몰랐을 정보 1개 이상"
    parts.append(
        "\n사용자가 몰랐을 법한 흥미로운 사실이나 맥락을 최소 1개 포함해주세요. "
        "한국어로 답변해줘."
    )

    return "\n".join(parts)


def build_recommendation_context(profile):
    """추천 시스템에 전달할 페르소나 특성 문자열을 생성한다."""
    name = profile.get("name", "사용자")
    age = profile.get("age", 25)
    gender = profile.get("gender", "남성")
    mbti = profile.get("mbti", "")
    expert_mode = profile.get("expert_mode", False)

    parts = [f"사용자 정보: {name}, {age}세, {gender}"]

    if expert_mode:
        parts.append("이 사용자는 전문가 모드로, 학술적이고 깊이 있는 장소를 선호합니다.")
    elif age <= 12:
        parts.append("이 사용자는 어린이라서 재미있고 체험 가능한 장소를 좋아합니다.")
    elif age <= 18:
        parts.append("이 사용자는 청소년으로, 흥미롭고 SNS에 올릴 만한 멋진 장소를 좋아합니다.")

    if mbti:
        mbti_upper = mbti.upper()
        preferences = []
        if mbti_upper[0:1] == "E":
            preferences.append("활기차고 사람이 많은 장소")
        elif mbti_upper[0:1] == "I":
            preferences.append("조용하고 사색적인 장소")
        if "N" in mbti_upper:
            preferences.append("역사적 상상력을 자극하는 장소")
        elif "S" in mbti_upper:
            preferences.append("구체적 유물과 실물을 볼 수 있는 장소")
        if "F" in mbti_upper:
            preferences.append("감동적인 이야기가 있는 장소")
        elif "T" in mbti_upper:
            preferences.append("건축 기술이나 과학적으로 흥미로운 장소")
        if preferences:
            parts.append(f"MBTI {mbti} 기반 선호: {', '.join(preferences)}")

    if not expert_mode:
        if gender == "남성":
            parts.append("건축 구조나 기술적 특징이 돋보이는 장소도 포함해줘.")
        elif gender == "여성":
            parts.append("예술적 아름다움이나 문화적 이야기가 풍부한 장소도 포함해줘.")

    return "\n".join(parts)


def build_activity_recommendation_context(profile):
    """액티비티 추천 시스템에 전달할 페르소나 특성 문자열을 생성한다."""
    name = profile.get("name", "사용자")
    age = profile.get("age", 25)
    gender = profile.get("gender", "남성")
    mbti = profile.get("mbti", "")

    parts = [f"사용자 정보: {name}, {age}세, {gender}"]

    if age <= 12:
        parts.append("이 사용자는 어린이라 체험형, 놀이공원, 동물원, 수족관 등을 좋아합니다.")
    elif age <= 18:
        parts.append("이 사용자는 청소년이라 어드벤처, 스릴 있는 체험, 인기 포토스팟을 좋아합니다.")
    elif age >= 60:
        parts.append("활동적이지 않고 여유롭게 즐길 수 있는 정원, 박물관, 전망대 등을 선호합니다.")
    elif age >= 40:
        parts.append("힐링형 액티비티(스파, 자연 관람, 문화 체험)를 선호합니다.")
    else:
        parts.append("다양한 체험과 볼거리를 좋아하는 연령대입니다.")

    if mbti:
        mbti_upper = mbti.upper()
        prefs = []
        if mbti_upper[0:1] == "E":
            prefs.append("사람들과 어울리는 활동, 공연, 축제")
        elif mbti_upper[0:1] == "I":
            prefs.append("조용한 산책, 박물관, 개인 체험")
        if "N" in mbti_upper:
            prefs.append("독특한 경험, 숨은 명소")
        elif "S" in mbti_upper:
            prefs.append("인기 명소, 검증된 액티비티")
        if "P" in mbti_upper:
            prefs.append("자유롭게 돌아볼 수 있는 곳")
        elif "J" in mbti_upper:
            prefs.append("일정이 짜여진 투어나 프로그램")
        if prefs:
            parts.append(f"MBTI {mbti} 기반 선호: {', '.join(prefs)}")

    return "\n".join(parts)


def build_food_recommendation_context(profile):
    """맛집 추천 시스템에 전달할 페르소나 특성 문자열을 생성한다."""
    name = profile.get("name", "사용자")
    age = profile.get("age", 25)
    gender = profile.get("gender", "남성")
    mbti = profile.get("mbti", "")

    parts = [f"사용자 정보: {name}, {age}세, {gender}"]

    if age <= 12:
        parts.append("이 사용자는 어린이라서 아이가 먹기 좋고 재미있는 메뉴가 있는 곳을 추천해줘.")
        parts.append("키즈 메뉴나 달콤한 디저트가 있는 곳이면 좋겠어.")
    elif age <= 18:
        parts.append("이 사용자는 청소년이라 가성비 좋고 SNS에 올릴 만한 비주얼이 좋은 곳을 추천해줘.")
    elif age >= 50:
        parts.append("건강하고 정갈한 음식, 조용한 분위기의 식당을 선호합니다.")
    else:
        parts.append("맛과 분위기 모두 좋은 곳을 추천해줘.")

    if mbti:
        mbti_upper = mbti.upper()
        prefs = []
        if mbti_upper[0:1] == "E":
            prefs.append("활기차고 분위기 좋은 곳")
        elif mbti_upper[0:1] == "I":
            prefs.append("조용하고 프라이빗한 곳")
        if "S" in mbti_upper:
            prefs.append("검증된 맛집, 리뷰가 많은 곳")
        elif "N" in mbti_upper:
            prefs.append("독특하고 새로운 컨셉의 곳")
        if "F" in mbti_upper:
            prefs.append("따뜻한 분위기, 감성적인 인테리어")
        elif "T" in mbti_upper:
            prefs.append("맛과 가성비가 확실한 곳")
        if prefs:
            parts.append(f"MBTI {mbti} 기반 선호: {', '.join(prefs)}")

    return "\n".join(parts)
