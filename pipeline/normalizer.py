import hashlib
import unicodedata
import re
from datetime import datetime, timezone
from sources.base import RawEvent

# Turkish month name mappings (full + abbreviated)
TR_MONTHS = {
    'ocak': 1, 'oca': 1,
    'şubat': 2, 'şub': 2,
    'mart': 3, 'mar': 3,
    'nisan': 4, 'nis': 4,
    'mayıs': 5, 'may': 5,
    'haziran': 6, 'haz': 6,
    'temmuz': 7, 'tem': 7,
    'ağustos': 8, 'ağu': 8,
    'eylül': 9, 'eyl': 9,
    'ekim': 10, 'eki': 10,
    'kasım': 11, 'kas': 11,
    'aralık': 12, 'ara': 12,
}

# Turkish day names (to strip)
TR_DAYS = ['pazartesi', 'salı', 'çarşamba', 'perşembe', 'cuma', 'cumartesi', 'pazar',
           'paz', 'pzt', 'sal', 'çar', 'per', 'cum', 'cmt']


def parse_turkish_date(text: str) -> str | None:
    """
    Parse Turkish date strings to ISO 8601 timestamps.
    Handles formats like:
      - "Mar 25, Çarşamba"     → 2026-03-25T00:00:00+00:00
      - "Nis 18, Cumartesi"    → 2026-04-18T00:00:00+00:00
      - "23 Mar - 27 Nis"      → 2026-03-23T00:00:00+00:00  (take first date)
      - "7 Nis - 9 Nis"        → 2026-04-07T00:00:00+00:00
      - "1 Nis - 1 May"        → 2026-04-01T00:00:00+00:00
    """
    if not text:
        return None

    text = text.strip()
    # Take first part if range (e.g. "23 Mar - 27 Nis")
    if ' - ' in text:
        text = text.split(' - ')[0].strip()

    # Normalize: lowercase, strip commas
    clean = text.lower().replace(',', ' ').replace('.', ' ')
    # Remove day names
    for day in TR_DAYS:
        clean = re.sub(r'\b' + day + r'\b', '', clean)
    clean = clean.strip()

    # Try to extract day + month (+ optional year)
    # Pattern: "25 mar" or "mar 25" or "25 mart" etc.
    tokens = clean.split()
    tokens = [t for t in tokens if t]

    day = None
    month = None
    year = datetime.now().year

    for token in tokens:
        if token.isdigit():
            num = int(token)
            if 1 <= num <= 31 and day is None:
                day = num
            elif num > 1000:
                year = num
        elif token in TR_MONTHS:
            month = TR_MONTHS[token]

    if day and month:
        # If the date has already passed this year, use next year
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if dt < now and (now - dt).days > 7:
                dt = datetime(year + 1, month, day, tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            return None

    return None


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
    """
    Converts RawEvent to a dict matching the actual DB schema.
    Actual schema uses source + source_id as unique key (no source_fingerprint).
    venue_id must be resolved separately via get_or_create_venue().
    """
    # Parse date from Turkish text
    start_time = raw.start_date
    if start_time and not _is_iso(start_time):
        start_time = parse_turkish_date(start_time)

    end_time = raw.end_date
    if end_time and not _is_iso(end_time):
        end_time = parse_turkish_date(end_time)

    return {
        # Events table columns
        'title': raw.title,
        'description': raw.description or '',
        'category': raw.category,
        'start_time': start_time,
        'end_time': end_time,
        'price_min': raw.price_min,
        'price_max': raw.price_max,
        'ticket_url': raw.ticket_url or '',
        'source': raw.source_id,       # e.g. "biletzero"
        'source_id': raw.external_id,  # slug/id from source site
        # Venue info (for upsert)
        'venue_name': raw.venue_name or 'Bilinmiyor',
        'venue_city': raw.venue_city or 'İstanbul',
        # Legacy fingerprint (kept for logging/dedup reference)
        'fingerprint': make_fingerprint(raw.title, raw.venue_name or '', raw.start_date or ''),
    }


def _is_iso(s: str) -> bool:
    """Check if string looks like an ISO datetime."""
    return bool(re.match(r'\d{4}-\d{2}-\d{2}', s))
