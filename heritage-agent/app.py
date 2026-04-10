"""On-Go (to Heritage): Heritage AI Tour Guide Agent."""

import os
import streamlit as st
from PIL import Image
from streamlit_folium import st_folium

from modules.gps_extractor import extract_gps
from modules.persona import (
    build_prompt, get_voice_key,
    build_recommendation_context,
    build_food_recommendation_context,
    build_activity_recommendation_context,
)
from modules.gemini_client import (
    generate_explanation, identify_place, recommend_nearby_places,
    recommend_nearby_food, recommend_nearby_activities,
    get_place_media, fetch_youtube_top_videos,
)
from modules.tts import text_to_speech
from modules.storage import (
    save_record, load_all_records, load_records_by_persona,
    save_profile, load_all_profiles, delete_profile,
    export_all_data, import_all_data, _get_gist_config,
    get_cached_explanation, save_cached_explanation,
)
from modules.place_matcher import (
    find_place_by_name, load_reference_text, list_known_place_names,
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
                col_enter, col_edit, col_del = st.columns(3)
                with col_enter:
                    if st.button("선택", key=f"select_{i}", use_container_width=True):
                        st.session_state["active_profile"] = prof
                        st.rerun()
                with col_edit:
                    if st.button("수정", key=f"edit_{i}", use_container_width=True):
                        st.session_state["editing_profile"] = prof
                        st.rerun()
                with col_del:
                    if st.button("삭제", key=f"delete_{i}", use_container_width=True):
                        delete_profile(prof["name"])
                        st.rerun()

    # 프로필 수정 폼
    if "editing_profile" in st.session_state:
        ep = st.session_state["editing_profile"]
        st.divider()
        st.subheader(f"✏️ '{ep['name']}' 프로필 수정")

        with st.form("edit_profile_form"):
            col1, col2 = st.columns(2)
            with col1:
                edit_name = st.text_input("이름", value=ep["name"])
                edit_age = st.number_input("나이", min_value=1, max_value=120, value=ep.get("age", 25))
            with col2:
                gender_options = ["남성", "여성", "기타"]
                edit_gender = st.selectbox("성별", gender_options, index=gender_options.index(ep.get("gender", "남성")))
                mbti_idx = MBTI_LIST.index(ep.get("mbti", "")) if ep.get("mbti", "") in MBTI_LIST else 0
                edit_mbti = st.selectbox("MBTI (선택사항)", MBTI_LIST, index=mbti_idx)
            edit_expert = st.checkbox("🎓 전문가 모드 (학술적 심층 설명)", value=ep.get("expert_mode", False))

            col_save, col_cancel = st.columns(2)
            with col_save:
                save_clicked = st.form_submit_button("저장", type="primary", use_container_width=True)
            with col_cancel:
                cancel_clicked = st.form_submit_button("취소", use_container_width=True)

            if save_clicked:
                if not edit_name.strip():
                    st.error("이름을 입력해주세요.")
                else:
                    # 기존 프로필 삭제 후 새로 저장
                    delete_profile(ep["name"])
                    updated = {
                        "name": edit_name.strip(),
                        "age": edit_age,
                        "gender": edit_gender,
                        "mbti": edit_mbti,
                        "expert_mode": edit_expert,
                    }
                    save_profile(updated)
                    st.session_state.pop("editing_profile", None)
                    st.rerun()
            if cancel_clicked:
                st.session_state.pop("editing_profile", None)
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


def render_place_media(query, location, cache_key):
    """장소 미디어(사진 검색 + 구글 지도 + YouTube TOP3)를 렌더링한다."""
    import urllib.parse

    if cache_key not in st.session_state:
        with st.spinner("사진/리뷰 영상/지도 정보를 찾고 있습니다..."):
            st.session_state[cache_key] = {
                "media": get_place_media(query, location),
                "videos": fetch_youtube_top_videos(
                    f"{query} {location}".strip() if location else query
                ),
            }

    data = st.session_state[cache_key]
    media = data["media"]
    videos = data["videos"]

    # 사진 검색 + 구글 지도 버튼
    col_i, col_m = st.columns(2)
    with col_i:
        st.link_button(
            "📷 사진 검색",
            media["image_search_url"],
            use_container_width=True,
        )
    with col_m:
        st.link_button(
            "🗺️ 구글 지도",
            media["map_url"],
            use_container_width=True,
        )

    # YouTube 인기 리뷰 영상 TOP 3 (Manifest #2: 시선은 유적에 → expander로 접어둠)
    with st.expander("🎥 인기 리뷰 영상 TOP 3"):
        if videos:
            for v in videos:
                view_str = f"{v['view_count']:,}" if v["view_count"] else "-"
                like_str = f"{v['like_count']:,}" if v["like_count"] else "-"
                cols = st.columns([1, 3])
                with cols[0]:
                    if v["thumbnail"]:
                        st.image(v["thumbnail"], use_container_width=True)
                with cols[1]:
                    st.markdown(f"**[{v['title']}]({v['url']})**")
                    st.caption(f"👁️ 조회수 {view_str}  ·  👍 좋아요 {like_str}")
        else:
            # API 키 없거나 실패 시 폴백: 조회수순 검색 링크
            q = urllib.parse.quote(f"{query} 리뷰")
            fallback_url = (
                f"https://www.youtube.com/results?search_query={q}&sp=CAMSAhAB"
            )
            st.info(
                "YouTube API 키(`YOUTUBE_API_KEY`)가 설정되지 않아 "
                "영상 목록을 직접 가져오지 못했습니다."
            )
            st.link_button(
                "🎥 YouTube에서 조회수순 검색",
                fallback_url,
                use_container_width=True,
            )


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
            st.session_state.pop("_rec_key", None)
            st.session_state.pop("_recommendations", None)
            st.session_state.pop("_selected_rec", None)
            st.session_state.pop("_food_key", None)
            st.session_state.pop("_food_recommendations", None)
            st.session_state.pop("_activity_key", None)
            st.session_state.pop("_activity_recommendations", None)
            st.session_state.pop("_forced_place_name", None)
            st.rerun()

    tab_guide, tab_food, tab_activity, tab_map = st.tabs([
        "📸 가이드", "🍽️ 추천 맛집", "🎡 액티비티", "🗺️ 지도 앨범"
    ])

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
                st.warning("AI가 장소를 인식하지 못했습니다. 직접 입력하거나 등록된 장소에서 선택해주세요.")
                place_name = st.text_input("장소 이름을 입력하세요", value="")

            # ── Premortem #4: 등록된 장소에서 직접 선택 폴백 ──
            # (AI 인식이 틀렸거나 공식 자료가 있는 장소를 명시적으로 고르고 싶을 때)
            known_names = list_known_place_names()
            if known_names:
                with st.expander("📚 등록된 장소에서 선택하기 (공식 자료 있는 장소)"):
                    picked = st.selectbox(
                        "자료가 등록된 장소",
                        options=["(선택 안 함)"] + known_names,
                        key="_known_place_picker",
                    )
                    if picked and picked != "(선택 안 함)":
                        if st.button(
                            f"✓ '{picked}'(으)로 장소 이름 설정",
                            use_container_width=True,
                        ):
                            st.session_state["_forced_place_name"] = picked
                            st.rerun()
                if st.session_state.get("_forced_place_name"):
                    place_name = st.session_state["_forced_place_name"]
                    st.info(f"✓ 선택된 장소: **{place_name}**")
                    if st.button("↺ 선택 해제", key="_clear_forced"):
                        st.session_state.pop("_forced_place_name", None)
                        st.rerun()

            if place_name:
                if st.button("🔍 설명 받기", type="primary", use_container_width=True):
                    place_location = ai_result.get("location", "") if ai_result else ""

                    # ── Data Integrity (Manifest #1): 로컬 발굴/관리 자료 조회 ──
                    matched_place = find_place_by_name(place_name)
                    reference_text = None
                    reference_source = None
                    if matched_place:
                        reference_text = load_reference_text(matched_place["data_file"])
                        if reference_text:
                            reference_source = matched_place["data_file"]

                    prompt = build_prompt(
                        profile, place_name, place_location,
                        reference_text=reference_text,
                    )

                    # ── Premortem #5: 응답 캐싱 (같은 장소+페르소나는 재사용) ──
                    cache_key_str = (
                        f"{place_name}|{profile.get('name', '')}|{profile.get('age', '')}"
                        f"|{profile.get('gender', '')}|{profile.get('mbti', '')}"
                        f"|{profile.get('expert_mode', False)}"
                    )
                    cached = get_cached_explanation(cache_key_str)
                    if cached:
                        explanation = cached
                        st.toast("💾 캐시된 설명을 불러왔습니다.", icon="⚡")
                    else:
                        with st.spinner("AI가 설명을 준비하고 있습니다..."):
                            explanation = generate_explanation(image, prompt)
                        save_cached_explanation(cache_key_str, explanation)

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
                        "reference_source": reference_source,
                    }
                    st.session_state["_result_lat"] = lat
                    st.session_state["_result_lng"] = lng
                    st.session_state.pop("_rec_key", None)
                    st.session_state.pop("_recommendations", None)
                    st.session_state.pop("_selected_rec", None)
                    st.session_state.pop("_food_key", None)
                    st.session_state.pop("_food_recommendations", None)
                    st.session_state.pop("_activity_key", None)
                    st.session_state.pop("_activity_recommendations", None)
        
                # 결과 표시
                if "result" in st.session_state:
                    result = st.session_state["result"]
                    st.divider()
                    location_str = f" ({result['location']})" if result.get("location") else ""
                    st.subheader(f"📍 {result['place_name']}{location_str}")
                    st.write(result["explanation"])

                    # ── Data Integrity: 참고 자료 출처 표시 (Manifest #1, Premortem #2) ──
                    if result.get("reference_source"):
                        st.caption(
                            f"📚 참고: `{result['reference_source']}` "
                            f"(공식 발굴/관리 자료 기반)"
                        )
                    else:
                        st.caption(
                            "📚 공식 참고 자료가 없는 장소입니다. "
                            "세부 사실은 별도 확인을 권장합니다."
                        )

                    st.audio(result["mp3_bytes"], format="audio/mp3")
                    st.success("✅ 방문 기록이 저장되었습니다!")

                    # ── 주변 유적지 추천 ──
                    st.divider()
                    st.subheader("🧭 주변 추천 유적지")

                    # 추천 로드 (캐싱)
                    rec_key = f"recs_{result['place_name']}"
                    if st.session_state.get("_rec_key") != rec_key:
                        with st.spinner("주변 유적지를 찾고 있습니다..."):
                            persona_ctx = build_recommendation_context(profile)
                            # 좌표는 result에서 가져옴
                            r_lat = st.session_state.get("_result_lat", 0)
                            r_lng = st.session_state.get("_result_lng", 0)
                            recs = recommend_nearby_places(
                                result["place_name"],
                                result.get("location", ""),
                                r_lat, r_lng,
                                persona_ctx,
                            )
                        st.session_state["_rec_key"] = rec_key
                        st.session_state["_recommendations"] = recs
                        st.session_state.pop("_selected_rec", None)
            
                    recs = st.session_state.get("_recommendations", [])

                    if recs:
                        CATEGORY_ICONS = {
                            "대학": "🎓", "종교건축": "⛪", "궁전": "🏰",
                            "유적지": "🏛️", "현대건축": "🏢", "탑": "🗼",
                            "다리": "🌉", "기념물": "🗽", "박물관": "🏛️",
                            "정원": "🌳", "기타": "📍",
                        }
                        for idx, rec in enumerate(recs):
                            cat_icon = CATEGORY_ICONS.get(rec.get("category", ""), "📍")
                            dist_str = f" | 📏 {rec['distance']}" if rec.get("distance") else ""
                            with st.container():
                                st.markdown(
                                    f"""
                                    <div style="padding:12px; border:1px solid #444;
                                                border-radius:10px; margin-bottom:8px;">
                                        <div style="font-size:18px; font-weight:bold;">
                                            {cat_icon} {rec['name']}
                                        </div>
                                        <div style="font-size:13px; color:#aaa; margin:4px 0;">
                                            📌 {rec.get('location', '')}{dist_str}
                                        </div>
                                        <div style="font-size:14px; margin:6px 0;">
                                            {rec.get('description', '')}
                                        </div>
                                        <div style="font-size:13px; color:#4CAF50;">
                                            💡 {rec.get('reason', '')}
                                        </div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )
                                if st.button(
                                    f"📖 자세히 보기",
                                    key=f"rec_detail_{idx}",
                                    use_container_width=True,
                                ):
                                    st.session_state["_selected_rec"] = idx
                                    st.rerun()

                        # 선택된 추천 장소 미디어 보기
                        if "_selected_rec" in st.session_state:
                            sel_idx = st.session_state["_selected_rec"]
                            sel = recs[sel_idx]
                            st.divider()
                            cat_icon = CATEGORY_ICONS.get(sel.get("category", ""), "📍")
                            st.subheader(f"{cat_icon} {sel['name']}")
                            st.caption(f"📌 {sel.get('location', '')} | 🏷️ {sel.get('category', '기타')}")

                            # 미디어 (사진 검색 + 구글 지도 + YouTube TOP3)
                            render_place_media(
                                query=sel.get("name", ""),
                                location=sel.get("location", ""),
                                cache_key=f"_rec_media_{sel_idx}",
                            )

                            if st.button("🔙 추천 목록으로 돌아가기", use_container_width=True):
                                st.session_state.pop("_selected_rec", None)
                                st.rerun()
                    else:
                        st.info("주변 추천 장소를 찾지 못했습니다.")

    # ── 🍽️ 추천 맛집 탭 ──
    with tab_food:
        if "result" not in st.session_state:
            st.info("👈 먼저 '가이드' 탭에서 사진을 올리고 장소 설명을 받아주세요.\n\n방문 중인 장소 주변의 맛집을 추천해드립니다.")
        else:
            result = st.session_state["result"]
            location_str = f" ({result['location']})" if result.get("location") else ""
            st.subheader(f"🍽️ {result['place_name']}{location_str} 주변 맛집")
            st.caption(f"{profile['name']}님의 취향에 맞게 인기 맛집 3곳을 추천해드려요")

            # 추천 로드 (캐싱)
            food_key = f"food_{result['place_name']}"
            if st.session_state.get("_food_key") != food_key:
                with st.spinner("주변 인기 맛집을 찾고 있습니다..."):
                    food_persona_ctx = build_food_recommendation_context(profile)
                    f_lat = st.session_state.get("_result_lat", 0)
                    f_lng = st.session_state.get("_result_lng", 0)
                    food_recs = recommend_nearby_food(
                        result["place_name"],
                        result.get("location", ""),
                        f_lat, f_lng,
                        food_persona_ctx,
                    )
                st.session_state["_food_key"] = food_key
                st.session_state["_food_recommendations"] = food_recs

            food_recs = st.session_state.get("_food_recommendations", [])

            if food_recs:
                FOOD_ICONS = {
                    "한식": "🍚", "양식": "🍝", "중식": "🥢", "일식": "🍣",
                    "카페": "☕", "디저트": "🍰", "분식": "🍢",
                    "해산물": "🦞", "퓨전": "🍽️", "기타": "🍴",
                }
                PRICE_ICONS = {"저렴": "💵", "보통": "💵💵", "고급": "💵💵💵"}
                RATING_ICONS = {"매우높음": "⭐⭐⭐", "높음": "⭐⭐", "보통": "⭐"}

                for idx, food in enumerate(food_recs):
                    food_icon = FOOD_ICONS.get(food.get("category", ""), "🍴")
                    price = PRICE_ICONS.get(food.get("price_range", ""), "")
                    rating = RATING_ICONS.get(food.get("rating", ""), "")

                    st.markdown(
                        f"""
                        <div style="padding:14px; border:1px solid #444;
                                    border-radius:10px; margin-bottom:10px;
                                    background-color: rgba(255,140,0,0.05);">
                            <div style="font-size:19px; font-weight:bold;">
                                {food_icon} {food['name']}
                            </div>
                            <div style="font-size:13px; color:#aaa; margin:4px 0;">
                                🏷️ {food.get('category', '')} | {price} | {rating}
                            </div>
                            <div style="font-size:14px; margin:8px 0;">
                                {food.get('description', '')}
                            </div>
                            <div style="font-size:13px; color:#FF8C00;">
                                💡 {food.get('reason', '')}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    # 미디어 (사진 검색 + 구글 지도 + YouTube TOP3)
                    render_place_media(
                        query=food["name"],
                        location=result.get("location", ""),
                        cache_key=f"_food_media_{idx}_{food_key}",
                    )

                    st.divider()
            else:
                st.info("주변 맛집을 찾지 못했습니다. 다른 장소를 시도해보세요.")

    # ── 🎡 액티비티 탭 ──
    with tab_activity:
        if "result" not in st.session_state:
            st.info("👈 먼저 '가이드' 탭에서 사진을 올리고 장소 설명을 받아주세요.\n\n방문 중인 장소 주변의 인기 액티비티를 추천해드립니다.")
        else:
            result = st.session_state["result"]
            location_str = f" ({result['location']})" if result.get("location") else ""
            st.subheader(f"🎡 {result['place_name']}{location_str} 주변 액티비티")
            st.caption(f"{profile['name']}님께 어울리는 인기 액티비티 3곳을 추천해드려요")

            # 추천 로드 (캐싱)
            activity_key = f"activity_{result['place_name']}"
            if st.session_state.get("_activity_key") != activity_key:
                with st.spinner("주변 인기 액티비티를 찾고 있습니다..."):
                    activity_persona_ctx = build_activity_recommendation_context(profile)
                    a_lat = st.session_state.get("_result_lat", 0)
                    a_lng = st.session_state.get("_result_lng", 0)
                    activity_recs = recommend_nearby_activities(
                        result["place_name"],
                        result.get("location", ""),
                        a_lat, a_lng,
                        activity_persona_ctx,
                    )
                st.session_state["_activity_key"] = activity_key
                st.session_state["_activity_recommendations"] = activity_recs

            activity_recs = st.session_state.get("_activity_recommendations", [])

            if activity_recs:
                ACTIVITY_ICONS = {
                    "공원": "🌳", "테마파크": "🎢", "전망대": "🌇",
                    "쇼핑": "🛍️", "야경": "🌃", "테마거리": "🛤️",
                    "투어": "🚌", "체험": "🎨", "스파": "💆",
                    "공연": "🎭", "동물원": "🦁", "수족관": "🐠",
                    "놀이공원": "🎠", "기타": "🎡",
                }
                DIFFICULTY_ICONS = {"쉬움": "🟢", "보통": "🟡", "활동적": "🔴"}

                for idx, act in enumerate(activity_recs):
                    act_icon = ACTIVITY_ICONS.get(act.get("category", ""), "🎡")
                    diff = DIFFICULTY_ICONS.get(act.get("difficulty", ""), "")
                    duration = act.get("duration", "")

                    st.markdown(
                        f"""
                        <div style="padding:14px; border:1px solid #444;
                                    border-radius:10px; margin-bottom:10px;
                                    background-color: rgba(100,150,255,0.05);">
                            <div style="font-size:19px; font-weight:bold;">
                                {act_icon} {act['name']}
                            </div>
                            <div style="font-size:13px; color:#aaa; margin:4px 0;">
                                🏷️ {act.get('category', '')} | ⏱️ {duration} | {diff} {act.get('difficulty', '')}
                            </div>
                            <div style="font-size:14px; margin:8px 0;">
                                {act.get('description', '')}
                            </div>
                            <div style="font-size:13px; color:#6496FF;">
                                💡 {act.get('reason', '')}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    # 미디어 (사진 검색 + 구글 지도 + YouTube TOP3)
                    render_place_media(
                        query=act["name"],
                        location=result.get("location", ""),
                        cache_key=f"_activity_media_{idx}_{activity_key}",
                    )

                    st.divider()
            else:
                st.info("주변 액티비티를 찾지 못했습니다. 다른 장소를 시도해보세요.")

    # ── 🗺️ 지도 앨범 탭 ──
    with tab_map:
        my_records = load_records_by_persona(profile["name"])
        m = create_map(my_records)
        st_folium(m, width=700, height=500, use_container_width=True)

        if my_records:
            st.divider()
            st.subheader(f"📋 {profile['name']}님의 방문 기록")
            for rec in sorted(my_records, key=lambda r: r["date"] + r["time"], reverse=True):
                location_str = f" - {rec.get('location', '')}" if rec.get("location") else ""
                with st.expander(
                    f"{rec['date']} - {rec['place_name']}{location_str}"
                ):
                    photo_path = os.path.join(
                        os.path.dirname(__file__), "user_data", "photos", rec.get("photo_filename", "")
                    )
                    if os.path.exists(photo_path):
                        st.image(photo_path, use_container_width=True)
                    st.write(rec["ai_explanation"])
        else:
            st.info(f"{profile['name']}님의 방문 기록이 없습니다. 가이드 탭에서 사진을 올려보세요!")

        # 데이터 저장 상태
        st.divider()
        token, gist_id = _get_gist_config()
        if token and gist_id:
            st.success("☁️ 클라우드 저장(GitHub Gist) 활성화 - 리붓해도 데이터가 유지됩니다")
        else:
            st.warning(
                "⚠️ 클라우드 저장이 설정되지 않았습니다. 앱 재시작 시 데이터가 초기화될 수 있습니다.\n\n"
                "영구 저장을 원하시면 Streamlit secrets에 `GITHUB_TOKEN`과 `GIST_ID`를 추가하세요. "
                "(Private Gist 생성 → PAT 발급 시 `gist` 스코프 체크)"
            )

        # 데이터 내보내기/가져오기
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
