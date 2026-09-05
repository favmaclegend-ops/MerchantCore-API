"""Seed demo billboard adverts (video ads) into the market database.

Idempotent: skips adverts whose ``video_url`` already exists in the table so
it can be re-run safely after the market DB grows.

All URLs below were verified reachable over HTTPS and, via ffprobe, are within
the required 10s–60s playback window:
  - media.w3.org/2010/05/sintel/trailer.mp4            (52s)
  - download.samplelib.com/mp4/sample-15s.mp4          (16s)
  - download.samplelib.com/mp4/sample-20s.mp4          (20s)
  - test-videos.co.uk/.../Big_Buck_Bunny_720_10s_1MB   (10s)
"""

import uuid
from datetime import UTC, datetime

from app.db.market_session import MarketSessionLocal
from app.models.market import MarketAdvert

DEMO_ADVERTS = [
    {
        "title": "Sintel Cinematic Trailer",
        "advert_url": "https://picsum.photos/seed/ad-sintel/900/360",
        "video_url": "https://media.w3.org/2010/05/sintel/trailer.mp4",
        "visit_link": "https://merchantcore-api.onrender.com",
    },
    {
        "title": "Escape Travel Co",
        "advert_url": "https://picsum.photos/seed/ad-escape/900/360",
        "video_url": "https://download.samplelib.com/mp4/sample-15s.mp4",
        "visit_link": "https://merchantcore-api.onrender.com",
    },
    {
        "title": "Fun Inside Meals",
        "advert_url": "https://picsum.photos/seed/ad-fun/900/360",
        "video_url": "https://download.samplelib.com/mp4/sample-20s.mp4",
        "visit_link": "https://merchantcore-api.onrender.com",
    },
    {
        "title": "Joyride Autos",
        "advert_url": "https://picsum.photos/seed/ad-joyride/900/360",
        "video_url": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4",
        "visit_link": "https://merchantcore-api.onrender.com",
    },
]


def seed_adverts() -> int:
    db = MarketSessionLocal()
    created = 0
    try:
        existing = {
            row.video_url
            for row in db.query(MarketAdvert).filter(MarketAdvert.video_url.isnot(None)).all()
        }
        now = datetime.now(UTC)
        for ad in DEMO_ADVERTS:
            if ad["video_url"] in existing:
                continue
            db.add(
                MarketAdvert(
                    id=str(uuid.uuid4()),
                    title=ad["title"],
                    advert_url=ad["advert_url"],
                    video_url=ad["video_url"],
                    visit_link=ad["visit_link"],
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            created += 1
        db.commit()
    finally:
        db.close()
    return created


if __name__ == "__main__":
    count = seed_adverts()
    print(f"Seeded {count} new advert(s) into market_adverts.")