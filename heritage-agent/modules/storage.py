"""방문 기록 저장/불러오기 모듈 - 글로벌 캐시로 리붓에도 복원 가능."""

import base64
import json
import os
from datetime import datetime
from io import BytesIO

import streamlit as st
from PIL import Image

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_data")
RECORDS_PATH = os.path.join(BASE_DIR, "records.json")
PROFILES_PATH = os.path.join(BASE_DIR, "profiles.json")
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")


def _ensure_dirs():
    os.makedirs(PHOTOS_DIR, exist_ok=True)


# ── 글로벌 캐시 (리붓 전까지 모든 세션 공유) ──

@st.cache_resource
def _get_global_store():
    """앱 전체에서 공유되는 글로벌 저장소. 리붓 전까지 유지."""
    return {
        "records": {"records": []},
        "profiles": {"profiles": []},
        "photos": {},  # {filename: base64_str}
    }


def _sync_from_disk():
    """디스크에 파일이 있으면 글로벌 캐시로 로드."""
    store = _get_global_store()
    if os.path.exists(RECORDS_PATH) and not store["records"]["records"]:
        with open(RECORDS_PATH, encoding="utf-8") as f:
            store["records"] = json.load(f)
    if os.path.exists(PROFILES_PATH) and not store["profiles"]["profiles"]:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            store["profiles"] = json.load(f)


def _save_to_disk():
    """글로벌 캐시를 디스크에도 백업."""
    _ensure_dirs()
    store = _get_global_store()
    with open(RECORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(store["records"], f, ensure_ascii=False, indent=2)
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(store["profiles"], f, ensure_ascii=False, indent=2)


# ── 방문 기록 ──

def _generate_record_id(data):
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"rec_{today}_"
    existing = [r["id"] for r in data["records"] if r["id"].startswith(prefix)]
    seq = len(existing) + 1
    return f"{prefix}{seq:03d}"


def save_record(photo, place_info, persona, explanation):
    """방문 기록을 저장한다."""
    _sync_from_disk()
    store = _get_global_store()
    data = store["records"]
    record_id = _generate_record_id(data)
    now = datetime.now()

    # 사진을 가로 800px로 리사이즈
    width = 800
    ratio = width / photo.width
    height = int(photo.height * ratio)
    resized = photo.resize((width, height), Image.LANCZOS)

    # 디스크 저장
    _ensure_dirs()
    photo_filename = f"{record_id}.jpg"
    resized.save(os.path.join(PHOTOS_DIR, photo_filename), "JPEG", quality=85)

    # 글로벌 캐시에 사진 base64로 저장 (리붓 후에도 사용 가능)
    buf = BytesIO()
    resized.save(buf, format="JPEG", quality=85)
    store["photos"][photo_filename] = base64.b64encode(buf.getvalue()).decode("utf-8")

    record = {
        "id": record_id,
        "photo_filename": photo_filename,
        "place_name": place_info.get("name", "알 수 없는 장소"),
        "location": place_info.get("location", ""),
        "lat": place_info.get("lat", 0),
        "lng": place_info.get("lng", 0),
        "category": place_info.get("category", "기타"),
        "persona": persona,
        "ai_explanation": explanation,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
    }

    data["records"].append(record)
    _save_to_disk()
    return record


def load_all_records():
    _sync_from_disk()
    store = _get_global_store()
    return store["records"]["records"]


def load_records_by_place(place_name):
    records = load_all_records()
    return [r for r in records if r["place_name"] == place_name]


def get_photo_base64(photo_filename):
    """사진의 base64 데이터를 반환한다. 캐시 또는 디스크에서."""
    store = _get_global_store()
    if photo_filename in store["photos"]:
        return store["photos"][photo_filename]
    path = os.path.join(PHOTOS_DIR, photo_filename)
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        store["photos"][photo_filename] = b64
        return b64
    return None


# ── 프로필 관리 ──

def save_profile(profile):
    _sync_from_disk()
    store = _get_global_store()
    data = store["profiles"]
    existing = [i for i, p in enumerate(data["profiles"]) if p["name"] == profile["name"]]
    if existing:
        data["profiles"][existing[0]] = profile
    else:
        data["profiles"].append(profile)
    _save_to_disk()


def load_all_profiles():
    _sync_from_disk()
    store = _get_global_store()
    return store["profiles"]["profiles"]


def delete_profile(name):
    _sync_from_disk()
    store = _get_global_store()
    data = store["profiles"]
    data["profiles"] = [p for p in data["profiles"] if p["name"] != name]
    _save_to_disk()


# ── 내보내기/가져오기 (리붓 후 복원용) ──

def export_all_data():
    """모든 데이터를 JSON으로 내보낸다."""
    _sync_from_disk()
    store = _get_global_store()
    return json.dumps({
        "records": store["records"],
        "profiles": store["profiles"],
        "photos": store["photos"],
    }, ensure_ascii=False, indent=2)


def import_all_data(json_str):
    """JSON 데이터를 가져와서 복원한다."""
    imported = json.loads(json_str)
    store = _get_global_store()

    if "records" in imported:
        store["records"] = imported["records"]
    if "profiles" in imported:
        store["profiles"] = imported["profiles"]
    if "photos" in imported:
        store["photos"] = imported["photos"]
        # 사진 파일도 디스크에 복원
        _ensure_dirs()
        for filename, b64 in imported["photos"].items():
            path = os.path.join(PHOTOS_DIR, filename)
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))

    _save_to_disk()
