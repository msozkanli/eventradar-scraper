import asyncio
import logging
from sources.biletzero import BiletzeroSource
from pipeline.normalizer import normalize
from pipeline.duplicate import is_duplicate
from pipeline.delta import detect_delta
from db.client import get_connection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s — %(message)s'
)
logger = logging.getLogger(__name__)

CITIES = ['istanbul', 'ankara', 'izmir', 'bursa', 'antalya']


async def run_scraper():
    conn = get_connection()
    source = BiletzeroSource()
    total_new = 0
    total_updated = 0

    for city in CITIES:
        logger.info(f"Scraping {city}...")
        try:
            events = await source.fetch_events(city=city)
            logger.info(f"{city}: {len(events)} events fetched")

            for raw in events:
                normalized = normalize(raw)
                fp = normalized['fingerprint']

                delta = detect_delta(conn, fp, normalized.get('price_min'))
                if delta:
                    logger.info(f"Price drop: {normalized['title']} {delta['old']}→{delta['new']}₺")
                    # TODO: notification oluştur

                if is_duplicate(conn, fp):
                    if delta:
                        # fiyat güncelle
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE events SET price_min=%s WHERE source_fingerprint=%s",
                                (normalized['price_min'], fp)
                            )
                        conn.commit()
                        total_updated += 1
                    continue

                # Yeni etkinlik ekle
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO events (
                            id, title, category, start_time, end_time,
                            price_min, price_max, image_url, ticket_url,
                            source_fingerprint, created_at
                        ) VALUES (
                            gen_random_uuid(), %(title)s, %(category)s, %(start_time)s, %(end_time)s,
                            %(price_min)s, %(price_max)s, %(image_url)s, %(ticket_url)s,
                            %(fingerprint)s, NOW()
                        )
                    """, normalized)
                conn.commit()
                total_new += 1
                logger.info(f"New: {normalized['title']}")

        except Exception as e:
            logger.error(f"Error scraping {city}: {e}", exc_info=True)

    conn.close()
    logger.info(f"Done. New: {total_new}, Updated: {total_updated}")
    return total_new, total_updated


if __name__ == '__main__':
    asyncio.run(run_scraper())
