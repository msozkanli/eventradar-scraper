import asyncio
import logging
import uuid
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


def get_or_create_venue(conn, name: str, city: str) -> str:
    """Upsert venue by name+city, return venue UUID."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM venues WHERE name = %s AND city = %s",
            (name, city)
        )
        row = cur.fetchone()
        if row:
            return str(row[0])
        # Create new venue with placeholder coords
        venue_id = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO venues (id, name, address, city, latitude, longitude)
               VALUES (%s, %s, %s, %s, 0.0, 0.0)""",
            (venue_id, name, city, city)
        )
        conn.commit()
        return venue_id


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
                src = normalized['source']
                src_id = normalized['source_id']

                delta = detect_delta(conn, src, src_id, normalized.get('price_min'))
                if delta:
                    logger.info(
                        f"Price drop: {normalized['title']} "
                        f"{delta['old']}→{delta['new']}₺"
                    )
                    # TODO: notification oluştur

                if is_duplicate(conn, src, src_id):
                    if delta:
                        # fiyat güncelle
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE events SET price_min=%s, updated_at=NOW() "
                                "WHERE source=%s AND source_id=%s",
                                (normalized['price_min'], src, src_id)
                            )
                        conn.commit()
                        total_updated += 1
                    continue

                # Skip events without a valid start_time
                if not normalized.get('start_time'):
                    logger.debug(f"Skipping (no date): {normalized['title']}")
                    continue

                # Get or create venue
                try:
                    venue_id = get_or_create_venue(
                        conn,
                        normalized['venue_name'],
                        normalized['venue_city']
                    )
                except Exception as e:
                    conn.rollback()
                    logger.warning(f"Venue upsert failed for {normalized['venue_name']}: {e}")
                    continue

                # Insert event
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO events (
                                id, title, description, category,
                                start_time, end_time,
                                price_min, price_max,
                                ticket_url, source, source_id,
                                venue_id, created_at, updated_at
                            ) VALUES (
                                gen_random_uuid(),
                                %(title)s, %(description)s, %(category)s,
                                %(start_time)s, %(end_time)s,
                                %(price_min)s, %(price_max)s,
                                %(ticket_url)s, %(source)s, %(source_id)s,
                                %(venue_id)s, NOW(), NOW()
                            )
                        """, {**normalized, 'venue_id': venue_id})
                    conn.commit()
                    total_new += 1
                    logger.info(f"New: {normalized['title'][:60]}")
                except Exception as e:
                    conn.rollback()
                    logger.warning(f"Insert failed for {normalized['title'][:40]}: {e}")

        except Exception as e:
            logger.error(f"Error scraping {city}: {e}", exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass

    conn.close()
    logger.info(f"Done. New: {total_new}, Updated: {total_updated}")
    return total_new, total_updated


if __name__ == '__main__':
    new, updated = asyncio.run(run_scraper())
    print(f"\n✅ Scraper complete — New: {new}, Updated: {updated}")
