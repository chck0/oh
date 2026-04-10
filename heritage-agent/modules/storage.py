"""방문 기록 저장/불러오기 모듈 - GitHub Gist로 리붓에도 영구 저장."""

import base64
import hashlib
import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from io import BytesIO

import streamlit as st
from PIL import Image

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_data")
RECORDS_PATH = os.path.join(BASE_DIR, "records.json")
PROFILES_PATH = os.path.join(BASE_DIR, "profiles.json")
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")

GIST_FILENAME = "on-go-data.json"

# Premortem #5: AI 응답 캐시 최대 엔트리 (무제한 누적 방지)
MAX_AI_CACHE_ENTRIES = 200


def _get_gist_config():
    """Streamlit secrets에서 Gist 설정을 가져온다."""
    try:
        token = st.secrets.get("GITHUB_TOKEN")
        gist_id = st.secrets.get("GIST_ID")
        return token, gist_id
    except Exception:
        return None, None


def _load_from_gist():
    """GitHub Gist에서 데이터를 로드한다."""
    token, gist_id = _get_gist_config()
    if not token or not gist_id:
        return None
    try:
        req = urllib.request.Request(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            files = data.get("files", {})
            if GIST_FILENAME in files:
                return json.loads(files[GIST_FILENAME]["content"])
    except Exception as e:
        print(f"[Gist Load Failed] {e}")
    return None


def _save_to_gist(store):
    """GitHub Gist에 데이터를 저장한다."""
    token, gist_id = _get_gist_config()
    if not token or not gist_id:
        return False
    try:
        content = json.dumps({
            "records": store["records"],
            "profiles": store["profiles"],
            "photos": store["photos"],
            "ai_cache": store.get("ai_cache", {}),
        }, ensure_ascii=False)

        body = json.dumps({
            "files": {GIST_FILENAME: {"content": content}}
        }).encode("utf-8")

        req = urllib.request.Request(
            f"https://api.github.com/gists/{gist_id}",
            data=body,
            method="PATCH",
            headers={
                "Authorization": f"token {token}",
                "Content-Type": "application/json",
            },
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[Gist Save Failed] {e}")
        return False


def _ensure_dirs():
    os.makedirs(PHOTOS_DIR, exist_ok=True)


# ── 글로벌 캐시 (리붓 전까지 모든 세션 공유) ──

@st.cache_resource
def _get_global_store():
    """앱 전체에서 공유되는 글로벌 저장소. 최초 호출 시 Gist/디스크에서 로드."""
    store = {
        "records": {"records": []},
        "profiles": {"profiles": []},
        "photos": {},
        "ai_cache": {},  # Premortem #5: 같은 장소+페르소나 응답 재사용
        "_gist_loaded": False,
    }

    # 1) Gist 우선 시도 (클라우드 영속성)
    gist_data = _load_from_gist()
    if gist_data:
        store["records"] = gist_data.get("records", {"records": []})
        store["profiles"] = gist_data.get("profiles", {"profiles": []})
        store["photos"] = gist_data.get("photos", {})
        store["ai_cache"] = gist_data.get("ai_cache", {})
        store["_gist_loaded"] = True
        return store

    # 2) 디스크 폴백 (로컬 개발)
    if os.path.exists(RECORDS_PATH):
        with open(RECORDS_PATH, encoding="utf-8") as f:
            store["records"] = json.load(f)
    if os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, encoding="utf-8") as f:
            store["profiles"] = json.load(f)

    return store


def _sync_from_disk():
    """이전 호환성을 위해 유지 (no-op)."""
    _get_global_store()


def _save_to_disk():
    """글로벌 캐시를 Gist(우선) 및 디스크에 백업."""
    store = _get_global_store()

    # 1) Gist에 저장 시도 (클라우드 영속성)
    _save_to_gist(store)

    # 2) 디스크에도 저장 (로컬 개발 및 로컬 백업)
    try:
        _ensure_dirs()
        with open(RECORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(store["records"], f, ensure_ascii=False, indent=2)
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(store["profiles"], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Disk Save Failed] {e}")


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


def load_records_by_persona(persona_name):
    records = load_all_records()
    return [r for r in records if r.get("persona") == persona_name]


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
        "ai_cache": store.get("ai_cache", {}),
    }, ensure_ascii=False, indent=2)


def import_all_data(json_str):
    """JSON 데이터를 가져와서 복원한다."""
    imported = json.loads(json_str)
    store = _get_global_store()

    if "records" in imported:
        store["records"] = imported["records"]
    if "profiles" in imported:
        store["profiles"] = imported["profiles"]
    if "ai_cache" in imported:
        store["ai_cache"] = imported["ai_cache"]
    if "photos" in imported:
        store["photos"] = imported["photos"]
        # 사진 파일도 디스크에 복원
        _ensure_dirs()
        for filename, b64 in imported["photos"].items():
            path = os.path.join(PHOTOS_DIR, filename)
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))

    _save_to_disk()


# ── AI 응답 캐시 (Premortem #5: 예산/할당량 절약) ──

def _hash_cache_key(cache_key_str):
    """긴 캐시 키 문자열을 짧은 해시로 변환한다."""
    return hashlib.sha1(cache_key_str.encode("utf-8")).hexdigest()[:16]


def get_cached_explanation(cache_key_str):
    """캐시된 Gemini 설명 응답을 반환한다. 없으면 None."""
    _sync_from_disk()
    store = _get_global_store()
    cache = store.get("ai_cache", {})
    key = _hash_cache_key(cache_key_str)
    entry = cache.get(key)
    if entry and isinstance(entry, dict):
        return entry.get("explanation")
    return None


def save_cached_explanation(cache_key_str, explanation):
    """Gemini 설명을 캐시에 저장하고 Gist에 동기화한다."""
    store = _get_global_store()
    cache = store.setdefault("ai_cache", {})
    key = _hash_cache_key(cache_key_str)
    cache[key] = {
        "explanation": explanation,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }

    # 최대 엔트리 초과 시 오래된 것부터 정리
    if len(cache) > MAX_AI_CACHE_ENTRIES:
        sorted_keys = sorted(
            cache.keys(),
            key=lambda k: cache[k].get("saved_at", ""),
        )
        for old_key in sorted_keys[: len(cache) - MAX_AI_CACHE_ENTRIES]:
            cache.pop(old_key, None)

    _save_to_disk()
