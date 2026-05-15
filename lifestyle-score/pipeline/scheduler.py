"""
POI 데이터 수집 스케줄러.
APScheduler를 사용해 주기적으로 카카오 로컬 API를 호출합니다.
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from kakao_local import fetch_all_poi

scheduler = BlockingScheduler(timezone="Asia/Seoul")

# 관심 좌표 목록 (추후 DB에서 동적으로 로드)
TARGET_LOCATIONS = [
    {"name": "강남역",  "lat": 37.4979, "lng": 127.0276},
    {"name": "홍대입구", "lat": 37.5563, "lng": 126.9228},
    {"name": "서울역",  "lat": 37.5547, "lng": 126.9707},
]


@scheduler.scheduled_job("cron", day_of_week="mon", hour=3, minute=0)
def collect_weekly():
    """매주 월요일 새벽 3시 POI 수집."""
    print("[스케줄러] 주간 POI 수집 시작")
    for loc in TARGET_LOCATIONS:
        poi = fetch_all_poi(lat=loc["lat"], lng=loc["lng"])
        total = sum(len(v) for v in poi.values())
        print(f"  {loc['name']}: {total}개 POI 수집 완료")
    print("[스케줄러] 수집 완료")


if __name__ == "__main__":
    print("스케줄러 시작 (매주 월요일 03:00)")
    scheduler.start()
