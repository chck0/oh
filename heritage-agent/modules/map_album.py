"""Folium 지도 앨범 생성 모듈 - 전세계 장소 대응."""

import base64
import os
from collections import defaultdict

import folium

PHOTOS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_data", "photos")
DEFAULT_CENTER = (37.5665, 126.9780)  # 서울 (기본값)
DEFAULT_ZOOM = 3  # 세계 전체 보기

CATEGORY_COLORS = {
    "대학": "blue",
    "종교건축": "purple",
    "궁전": "red",
    "유적지": "orange",
    "현대건축": "green",
    "탑": "darkred",
    "다리": "cadetblue",
    "기념물": "darkpurple",
    "기타": "gray",
}


def _photo_to_base64(photo_filename):
    path = os.path.join(PHOTOS_DIR, photo_filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _build_popup_html(place_name, records):
    location = records[0].get("location", "")
    header = f"{place_name}<br><small>{location}</small>" if location else place_name
    html_parts = [f'<div style="width:250px"><h4>{header}</h4>']

    for rec in records[:5]:
        b64 = _photo_to_base64(rec["photo_filename"])
        if b64:
            html_parts.append(
                f'<img src="data:image/jpeg;base64,{b64}" width="230">'
            )
        html_parts.append(
            f'<p style="font-size:12px;color:gray;">{rec["date"]} 방문</p>'
        )
        explanation_preview = rec["ai_explanation"][:100]
        html_parts.append(
            f'<p style="font-size:13px;">{explanation_preview}...</p>'
        )

    html_parts.append("</div>")
    return "\n".join(html_parts)


def create_map(records):
    """방문 기록들을 Folium 지도에 표시한다."""
    if not records:
        m = folium.Map(location=DEFAULT_CENTER, zoom_start=DEFAULT_ZOOM)
        folium.Marker(
            location=DEFAULT_CENTER,
            popup="아직 방문 기록이 없습니다. 가이드 탭에서 사진을 올려보세요!",
            icon=folium.Icon(color="gray", icon="info-sign"),
        ).add_to(m)
        return m

    # 유효한 좌표가 있는 기록들로 중심 계산
    valid = [r for r in records if r.get("lat") and r.get("lng")]
    if valid:
        avg_lat = sum(r["lat"] for r in valid) / len(valid)
        avg_lng = sum(r["lng"] for r in valid) / len(valid)
        center = (avg_lat, avg_lng)
        zoom = 4 if len(valid) > 1 else 15
    else:
        center = DEFAULT_CENTER
        zoom = DEFAULT_ZOOM

    m = folium.Map(location=center, zoom_start=zoom)

    # 같은 장소의 기록을 그룹화
    grouped = defaultdict(list)
    for rec in records:
        grouped[rec["place_name"]].append(rec)

    for place_name, place_records in grouped.items():
        first = place_records[0]
        lat = first.get("lat", 0)
        lng = first.get("lng", 0)
        if not lat and not lng:
            continue

        color = CATEGORY_COLORS.get(first.get("category", ""), "gray")
        popup_html = _build_popup_html(place_name, place_records)
        popup = folium.Popup(popup_html, max_width=280)

        folium.Marker(
            location=(lat, lng),
            popup=popup,
            icon=folium.Icon(color=color, icon="flag"),
        ).add_to(m)

    return m
