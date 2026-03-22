import hashlib
import unicodedata
import re
from sources.base import RawEvent


def normalize_title(title: str) -> str:
    """Lowercase, unicode normalize, remove punctuation."""
    title = title.lower()
    title = unicodedata.normalize('NFKD', title)
    title = re.sub(r'[^\w\s]', '', title)
    return title.strip()


def make_fingerprint(title: str, venue: str, date: str) -> str:
    raw = f"{normalize_title(title)}|{venue.lower() if venue else ''}|{date[:10] if date else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def normalize(raw: RawEvent) -> dict:
    return {
        'title': raw.title,
        'category': raw.category,
        'start_time': raw.start_date,
        'end_time': raw.end_date,
        'price_min': raw.price_min,
        'price_max': raw.price_max,
        'image_url': raw.image_url,
        'ticket_url': raw.ticket_url,
        'source_id': raw.source_id,
        'external_id': raw.external_id,
        'fingerprint': make_fingerprint(raw.title, raw.venue_name or '', raw.start_date or ''),
        'venue_name': raw.venue_name,
        'venue_city': raw.venue_city or 'İstanbul',
    }
