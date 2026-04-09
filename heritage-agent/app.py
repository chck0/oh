"""On-Go (to Heritage): Heritage AI Tour Guide Agent."""

import os
import streamlit as st
from PIL import Image
from streamlit_folium import st_folium

from modules.gps_extractor import extract_gps
from modules.persona import build_prompt, get_voice_key
from modules.gemini_client import generate_explanation, identify_place, generate_historical_image
from modules.tts import text_to_speech
from modules.storage import (
    save_record, load_all_records,
    save_profile, load_all_profiles, delete_profile,
    export_all_data, import_all_data,
)
from modules.map_album import create_map

st.set_page_config(page_title="On-Go (to Heritage)", layout="centered")

GENDER_ICONS = {"남성": "👨", "여성": "👩", "기타": "🧑"}
MBTI_LIST = [
    "", "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]


# ── 프로필 선택/생성 화면 ──
def show_profile_screen():
    st.markdown(
        """
        <style>
        .title-center { text-align: center; margin-bottom: 5px; }
        .subtitle-center { text-align: center; color: #888; margin-bottom: 30px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<h1 class="title-center">On-Go (to Heritage)</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle-center">누가 사용하나요?</p>', unsafe_allow_html=True)

    profiles = load_all_profiles()

    # 기존 프로필 표시
    if profiles:
        cols = st.columns(min(len(profiles), 4))
        for i, prof in enumerate(profiles):
            with cols[i % 4]:
                icon = GENDER_ICONS.get(prof.get("gender", ""), "🧑")
                expert_badge = " ⭐" if prof.get("expert_mode") else ""
                mbti_str = f" | {prof['mbti']}" if prof.get("mbti") else ""
                st.markdown(
                    f"""
                    <div style="text-align:center; padding:15px; border:2px solid #333;
                                border-radius:15px; margin-bottom:10px;">
                        <div style="font-size:50px;">{icon}</div>
                        <div style="font-size:16px; font-weight:bold; margin-top:5px;">
                            {prof['name']}{expert_badge}
                        </div>
                        <div style="font-size:12px; color:#888;">
                            {prof.get('age', '')}세 | {prof.get('gender', '')}{mbti_str}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                col_enter, col_del = st.columns(2)
                with col_enter:
                    if st.button("선택", key=f"select_{i}", use_container_width=True):
                        st.session_state["active_profile"] = prof
                        st.rerun()
                with col_del:
                    if st.button("삭제", key=f"delete_{i}", use_container_width=True):
                        delete_profile(prof["name"])
                        st.rerun()

    # 새 프로필 추가 폼
    st.divider()
    st.subheader("➕ 새 프로필 만들기")

    with st.form("new_profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("이름", placeholder="홍길동")
            new_age = st.number_input("나이", min_value=1, max_value=120, value=25)
        with col2:
            new_gender = st.selectbox("성별", ["남성", "여성", "기타"])
            new_mbti = st.selectbox("MBTI (선택사항)", MBTI_LIST)
        new_expert = st.checkbox("🎓 전문가 모드 (학술적 심층 설명)")

        submitted = st.form_submit_button("프로필 만들기", type="primary", use_container_width=True)
        if submitted:
            if not new_name.strip():
                st.error("이름을 입력해주세요.")
            else:
                profile = {
                    "name": new_name.strip(),
                    "age": new_age,
                    "gender": new_gender,
                    "mbti": new_mbti,
                    "expert_mode": new_expert,
                }
                save_profile(profile)
                st.session_state["active_profile"] = profile
                st.rerun()


# ── 메인 앱 화면 ──
def show_main_app():
    profile = st.session_state["active_profile"]
    icon = GENDER_ICONS.get(profile.get("gender", ""), "🧑")
    voice_key = get_voice_key(profile)

    # 상단 헤더
    header_col1, header_col2 = st.columns([4, 1])
    with header_col1:
        st.title("On-Go (to Heritage)")
        expert_str = " | 🎓 전문가 모드" if profile.get("expert_mode") else ""
        mbti_str = f" | {profile['mbti']}" if profile.get("mbti") else ""
        st.caption(f"{icon} {profile['name']} ({profile['age']}세{mbti_str}{expert_str})")
    with header_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 전환", use_container_width=True):
            st.session_state.pop("active_profile", None)
            st.session_state.pop("result", None)
            st.session_state.pop("_identify_key", None)
            st.rerun()

    tab_guide, tab_map = st.tabs(["📸 가이드", "🗺️ 지도 앨범"])

    # ── 📸 가이드 탭 ──
    with tab_guide:
        uploaded = st.file_uploader("건물/유적지 사진을 올려주세요", type=["jpg", "jpeg", "png"])

        if uploaded:
            image = Image.open(uploaded)
            st.image(image, use_container_width=True)

            # GPS 추출
            gps = extract_gps(image)

            # AI 이미지 인식 (캐싱)
            upload_key = uploaded.name + str(uploaded.size)
            if st.session_state.get("_identify_key") != upload_key:
                with st.spinner("🔍 사진 속 장소를 AI가 분석하고 있습니다..."):
                    ai_result = identify_place(image, gps)
                st.session_state["_identify_key"] = upload_key
                st.session_state["_identify_result"] = ai_result
                st.session_state.pop("result", None)
                st.session_state.pop("historical_img", None)
                st.session_state.pop("historical_error", None)
            else:
                ai_result = st.session_state.get("_identify_result")

            # 인식 결과 표시
            st.subheader("📍 장소 인식 결과")

            if gps:
                st.info(f"🛰️ GPS 감지: 위도 {gps['lat']:.4f}, 경도 {gps['lng']:.4f}")

            if ai_result:
                confidence_emoji = {"높음": "🟢", "보통": "🟡", "낮음": "🔴"}.get(
                    ai_result.get("confidence", ""), "⚪"
                )
                coord_str = ""
                if ai_result.get("lat") and ai_result.get("lng"):
                    coord_str = f"\n\n🗺️ 추정 좌표: ({ai_result['lat']:.4f}, {ai_result['lng']:.4f})"
                st.success(
                    f"🤖 AI 인식: **{ai_result['name']}**\n\n"
                    f"📌 위치: {ai_result.get('location', '알 수 없음')} | "
                    f"🏷️ 분류: {ai_result.get('category', '기타')} | "
                    f"{confidence_emoji} 확신도: {ai_result.get('confidence', '알 수 없음')}\n\n"
                    f"💡 근거: {ai_result.get('description', '')}"
                    f"{coord_str}"
                )
                place_name = st.text_input("장소 이름을 확인하거나 수정하세요", value=ai_result["name"])
            else:
                st.warning("AI가 장소를 인식하지 못했습니다. 직접 입력해주세요.")
                place_name = st.text_input("장소 이름을 입력하세요", value="")

            if place_name:
                if st.button("🔍 설명 받기", type="primary", use_container_width=True):
                    place_location = ai_result.get("location", "") if ai_result else ""
                    prompt = build_prompt(profile, place_name, place_location)

                    with st.spinner("AI가 설명을 준비하고 있습니다..."):
                        explanation = generate_explanation(image, prompt)

                    with st.spinner("음성을 생성하고 있습니다..."):
                        mp3_bytes = text_to_speech(explanation, voice_key)

                    # 좌표 결정
                    if gps:
                        lat, lng = gps["lat"], gps["lng"]
                    elif ai_result and ai_result.get("lat") and ai_result.get("lng"):
                        lat, lng = ai_result["lat"], ai_result["lng"]
                    else:
                        lat, lng = 0, 0

                    place_info = {
                        "name": place_name,
                        "location": ai_result.get("location", "") if ai_result else "",
                        "category": ai_result.get("category", "기타") if ai_result else "기타",
                        "lat": lat,
                        "lng": lng,
                    }
                    save_record(image, place_info, profile["name"], explanation)

                    st.session_state["result"] = {
                        "place_name": place_name,
                        "location": place_info["location"],
                        "explanation": explanation,
                        "mp3_bytes": mp3_bytes,
                        "voice_key": voice_key,
                    }

                # 결과 표시
                if "result" in st.session_state:
                    result = st.session_state["result"]
                    st.divider()
                    location_str = f" ({result['location']})" if result.get("location") else ""
                    st.subheader(f"📍 {result['place_name']}{location_str}")
                    st.write(result["explanation"])
                    st.audio(result["mp3_bytes"], format="audio/mp3")
                    st.success("✅ 방문 기록이 저장되었습니다!")

                    # 역사 재현 버튼
                    if "historical_img" not in st.session_state:
                        if st.button("🎨 그 시대의 모습 재현하기", type="primary", use_container_width=True):
                            with st.spinner("🎨 그 시대의 모습을 재현하고 있습니다..."):
                                img_result = generate_historical_image(
                                    image, result["place_name"], result["location"],
                                    result.get("voice_key", "adult_male"),
                                )
                            if isinstance(img_result, dict) and "error" in img_result:
                                st.session_state["historical_error"] = img_result["error"]
                            else:
                                st.session_state["historical_img"] = img_result
                            st.rerun()

                    # 에러 표시
                    if st.session_state.get("historical_error"):
                        st.error(f"⚠️ {st.session_state['historical_error']}")

                    # 역사 재현 이미지 표시
                    if st.session_state.get("historical_img"):
                        st.divider()
                        st.subheader("🏛️ 그 시대의 모습")
                        col_now, col_past = st.columns(2)
                        with col_now:
                            st.caption("📸 현재")
                            st.image(image, use_container_width=True)
                        with col_past:
                            st.caption("🎨 AI 재현")
                            st.image(st.session_state["historical_img"], use_container_width=True)

    # ── 🗺️ 지도 앨범 탭 ──
    with tab_map:
        records = load_all_records()
        m = create_map(records)
        st_folium(m, width=700, height=500, use_container_width=True)

        if records:
            st.divider()
            st.subheader("📋 방문 기록")
            for rec in sorted(records, key=lambda r: r["date"] + r["time"], reverse=True):
                location_str = f" - {rec.get('location', '')}" if rec.get("location") else ""
                with st.expander(
                    f"{rec['date']} - {rec['place_name']}{location_str} "
                    f"({rec.get('persona', '')})"
                ):
                    photo_path = os.path.join(
                        os.path.dirname(__file__), "user_data", "photos", rec.get("photo_filename", "")
                    )
                    if os.path.exists(photo_path):
                        st.image(photo_path, use_container_width=True)
                    st.write(rec["ai_explanation"])
        else:
            st.info("아직 방문 기록이 없습니다. 가이드 탭에서 사진을 올려보세요!")

        # 데이터 내보내기/가져오기
        st.divider()
        st.subheader("💾 데이터 백업")
        col_export, col_import = st.columns(2)
        with col_export:
            data_json = export_all_data()
            st.download_button(
                "📥 데이터 내보내기",
                data=data_json,
                file_name="on-go_backup.json",
                mime="application/json",
                use_container_width=True,
            )
        with col_import:
            uploaded_backup = st.file_uploader(
                "📤 데이터 가져오기",
                type=["json"],
                key="backup_upload",
                label_visibility="collapsed",
            )
            if uploaded_backup:
                if st.button("📤 복원하기", use_container_width=True):
                    import_all_data(uploaded_backup.read().decode("utf-8"))
                    st.success("✅ 데이터가 복원되었습니다!")
                    st.rerun()


# ── 라우팅 ──
if "active_profile" not in st.session_state:
    show_profile_screen()
else:
    show_main_app()
