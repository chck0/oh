"""
카카오 로컬 API로 수집한 POI를 PostgreSQL에 저장합니다.
"""

import os
import psycopg2
from dotenv import load_dotenv
from kakao_local import fetch_all_poi

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def save_poi(conn, items: list[dict]):
    """POI 목록을 DB에 저장합니다. 중복은 무시합니다."""
    sql = """
        INSERT INTO poi (name, category, lat, lng, location)
        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ON CONFLICT DO NOTHING
    """
    with conn.cursor() as cur:
        for item in items:
            cur.execute(sql, (
                item["name"],
                item["category"],
                item["lat"],
                item["lng"],
                item["lng"],
                item["lat"],
            ))
    conn.commit()


def collect_and_save(lat: float, lng: float, label: str = ""):
    """특정 좌표의 POI를 수집해 DB에 저장합니다."""
    print(f"\n[수집 시작] {label or f'{lat},{lng}'}")
    all_poi = fetch_all_poi(lat=lat, lng=lng, radius=1000)

    conn = get_conn()
    total = 0
    for category, items in all_poi.items():
        save_poi(conn, items)
        print(f"  {category}: {len(items)}개 저장")
        total += len(items)
    conn.close()

    print(f"  → 합계 {total}개 완료")
    return total


if __name__ == "__main__":
    # 테스트 좌표 3곳
    locations = [
        {"label": "강남역",   "lat": 37.4979, "lng": 127.0276},
        {"label": "홍대입구", "lat": 37.5563, "lng": 126.9228},
        {"label": "서울역",   "lat": 37.5547, "lng": 126.9707},
    ]

    for loc in locations:
        collect_and_save(lat=loc["lat"], lng=loc["lng"], label=loc["label"])

    print("\n✅ 전체 수집 완료")
