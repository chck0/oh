"""Gemini API 호출 모듈 - 전세계 건물/랜드마크 인식, 설명 생성, 역사 이미지 재현."""

import os
from io import BytesIO

import google.generativeai as genai
from google import genai as genai2
from google.genai import types as genai2_types
from PIL import Image as PILImage
from dotenv import load_dotenv

load_dotenv()

# Streamlit Cloud: st.secrets / 로컬: .env
try:
    import streamlit as st
    _API_KEY = st.secrets.get("GEMINI_API_KEY")
except Exception:
    _API_KEY = None

if not _API_KEY:
    _API_KEY = os.getenv("GEMINI_API_KEY")

if _API_KEY:
    genai.configure(api_key=_API_KEY)
    _genai2_client = genai2.Client(api_key=_API_KEY, http_options={"api_version": "v1alpha"})
else:
    _genai2_client = None

MODEL_NAME = "gemini-2.5-flash"
IMAGE_MODEL_NAME = "gemini-2.0-flash-preview-image-generation"


def generate_explanation(image, prompt):
    """사진과 프롬프트를 Gemini에 보내고 설명 텍스트를 받는다."""
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([prompt, image])
        return response.text
    except Exception as e:
        return f"⚠️ AI 설명 생성에 실패했습니다. 잠시 후 다시 시도해주세요.\n(오류: {e})"


def identify_place(image, gps_info=None):
    """사진 속 건물/랜드마크를 Gemini로 인식하고 좌표도 추정한다.

    Args:
        image: PIL Image 객체
        gps_info: {"lat": float, "lng": float} 또는 None

    Returns:
        {"name": str, "location": str, "confidence": str,
         "description": str, "category": str, "lat": float, "lng": float}
        또는 인식 실패 시 None
    """
    gps_hint = ""
    if gps_info:
        gps_hint = f"\n참고: 이 사진의 GPS 좌표는 위도 {gps_info['lat']:.4f}, 경도 {gps_info['lng']:.4f} 입니다.\n"

    prompt = (
        "이 사진에 보이는 건물, 랜드마크, 유적지, 기념물 등을 분석해줘.\n"
        f"{gps_hint}\n"
        "전세계 어떤 건물이든 가능해. 대학 건물, 성당, 궁전, 탑, 다리, 현대 건축물 등 모두 포함.\n"
        "반드시 아래 형식으로만 답해줘 (다른 말 하지 마):\n"
        "이름: [건물/장소의 공식 명칭]\n"
        "위치: [도시, 국가]\n"
        "위도: [숫자, 예: 37.4419]\n"
        "경도: [숫자, 예: -122.1430]\n"
        "분류: [대학, 종교건축, 궁전, 유적지, 현대건축, 탑, 다리, 기념물, 기타 중 택1]\n"
        "확신도: [높음/보통/낮음]\n"
        "근거: [사진에서 어떤 특징을 보고 판단했는지 한 줄로]"
    )
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([prompt, image])
        text = response.text.strip()

        result = {}
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("이름:"):
                result["name"] = line.replace("이름:", "").strip()
            elif line.startswith("위치:"):
                result["location"] = line.replace("위치:", "").strip()
            elif line.startswith("위도:"):
                try:
                    result["lat"] = float(line.replace("위도:", "").strip())
                except ValueError:
                    pass
            elif line.startswith("경도:"):
                try:
                    result["lng"] = float(line.replace("경도:", "").strip())
                except ValueError:
                    pass
            elif line.startswith("분류:"):
                result["category"] = line.replace("분류:", "").strip()
            elif line.startswith("확신도:"):
                result["confidence"] = line.replace("확신도:", "").strip()
            elif line.startswith("근거:"):
                result["description"] = line.replace("근거:", "").strip()

        if "name" in result:
            return result
        return None
    except Exception:
        return None


PERSONA_IMAGE_STYLE = {
    "child": (
        "Draw this in a colorful, friendly cartoon/illustration style "
        "like a children's picture book. Use bright warm colors, "
        "cute simplified characters in historical clothing, "
        "and a cheerful magical atmosphere. Add fun details a child would enjoy."
    ),
    "teenager": (
        "Render this in a dramatic anime/webtoon style. "
        "Use dynamic lighting and cinematic composition. "
        "Show cool historical characters in action poses. "
        "Make it look like a scene from an epic historical manga or game."
    ),
    "adult_male": (
        "Generate a photorealistic architectural reconstruction. "
        "Focus on structural details, construction techniques, and engineering. "
        "Use dramatic lighting to highlight the building's form and scale. "
        "Include period-accurate technical details."
    ),
    "adult_female": (
        "Create a beautiful, atmospheric watercolor-style painting. "
        "Focus on the artistic beauty and emotional mood of the era. "
        "Show the daily life of people, with soft warm lighting "
        "and romantic historical atmosphere. Include cultural and fashion details."
    ),
    "expert": (
        "Generate a precise academic architectural reconstruction. "
        "Use a style similar to historical survey illustrations or "
        "archaeological reconstruction drawings. Show accurate period details, "
        "original materials, colors based on historical records, and annotations."
    ),
}


def generate_historical_image(image, place_name, place_location="", voice_key="adult_male"):
    """현재 사진을 기반으로 페르소나에 맞는 역사 재현 이미지를 생성한다.

    Args:
        image: PIL Image 객체 (현재 사진)
        place_name: 건물/장소 이름
        place_location: 위치 정보
        voice_key: 페르소나 키 (이미지 스타일 결정)

    Returns:
        PIL Image 객체 (생성된 역사 재현 이미지) 또는 None
    """
    if not _genai2_client:
        return {"error": "API 클라이언트가 초기화되지 않았습니다. API 키를 확인해주세요."}

    location_info = f" in {place_location}" if place_location else ""
    style = PERSONA_IMAGE_STYLE.get(voice_key, PERSONA_IMAGE_STYLE["adult_male"])

    prompt = (
        f"Based on this photo of {place_name}{location_info}, "
        f"generate an image showing what this exact place "
        f"looked like during its peak historical period or when it was first built. "
        f"Keep the same angle and composition as the original photo. "
        f"{style}"
    )

    try:
        response = _genai2_client.models.generate_content(
            model=IMAGE_MODEL_NAME,
            contents=[prompt, image],
            config=genai2_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # 응답에서 이미지 파트 추출
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                img_bytes = part.inline_data.data
                return PILImage.open(BytesIO(img_bytes))

        return {"error": "AI가 이미지를 생성하지 못했습니다. 다른 사진으로 시도해보세요."}
    except Exception as e:
        return {"error": f"이미지 생성 실패: {e}"}
