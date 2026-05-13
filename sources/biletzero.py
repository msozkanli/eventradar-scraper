import re
import logging
from typing import Optional
from playwright.async_api import async_playwright
from .base import EventSource, RawEvent

logger = logging.getLogger(__name__)

CATEGORY_MAP = {
    'konser': 'Konser',
    'muzik': 'Müzik',
    'tiyatro': 'Tiyatro',
    'stand-up': 'Stand-up',
    'festival': 'Festival',
    'atolye': 'Workshop',
    'cocuk-aile': 'Çocuk & Aile',
    'party': 'Eğlence',
    'egitim': 'Eğitim',
    'yarisma': 'Yarışma',
    'yemekli-eglence': 'Yemek',
}

BASE_URL = "https://biletzero.com"


def parse_category_and_id(url: str) -> tuple[str, str]:
    """
    Parse category and external_id from a biletzero event URL.
    e.g. /tr/etkinlikler/konser/emre-altug-... -> ('Konser', 'emre-altug-...')
    """
    # Remove query string
    path = url.split('?')[0].rstrip('/')
    parts = path.split('/')
    # Expected: ['', 'tr', 'etkinlikler', '<category>', '<slug>']
    if len(parts) >= 5:
        cat_slug = parts[3]
        event_slug = parts[4]
        category = CATEGORY_MAP.get(cat_slug, cat_slug.capitalize())
        return category, event_slug
    elif len(parts) == 4:
        # No category in URL
        return 'Diğer', parts[3]
    return 'Diğer', path


def parse_price(text: str) -> tuple[Optional[int], Optional[int]]:
    """Extract min and max price from price text like '150 TL - 350 TL'."""
    if not text:
        return None, None
    numbers = re.findall(r'[\d.]+', text.replace('.', '').replace(',', ''))
    prices = []
    for n in numbers:
        try:
            prices.append(int(n))
        except ValueError:
            pass
    if not prices:
        return None, None
    return min(prices), max(prices)


class BiletzeroSource(EventSource):
    @property
    def source_id(self) -> str:
        return "biletzero"

    async def fetch_events(self, city: str = None) -> list[RawEvent]:
        city_slug = city.lower() if city else 'turkiye'
        url = f"{BASE_URL}/tr/etkinlikler/{city_slug}?sort=StartDate&sortDir=asc"
        events = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()

            logger.info(f"Fetching list page: {url}")
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
            except Exception as e:
                logger.warning(f"Timeout/error loading {url}: {e}")

            # Scroll to load more events
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)

            # Try various selectors for event cards
            raw_items = []

            # Try to find event links — detail pages have 6+ path segments
            links = await page.query_selector_all('a[href*="/tr/etkinlikler/"]')
            seen_urls = set()
            for link in links:
                href = await link.get_attribute('href')
                if not href:
                    continue
                # Must be a detail page (has 6+ path segments: /tr/etkinlikler/category/slug/city/session)
                path = href.split('?')[0].rstrip('/')
                parts = path.split('/')
                if len(parts) < 6:
                    continue
                full_url = href if href.startswith('http') else BASE_URL + href
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # biletzero link text format: "Mar 26, Perşembe\nKaraoke & Pong Night Takvimi"
                raw_text = (await link.inner_text()).strip()
                lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                # Take the non-date line (second line usually)
                non_date = [l for l in lines if not re.match(
                    r'^(\d{1,2}\s+\w{3}|\w{3}\s+\d{1,2}|\d{1,2}\s+\w+\s*[-–])', l
                ) and len(l) > 5]
                title = non_date[0] if non_date else (lines[-1] if lines else '')
                # Also try date from first line
                date_lines = [l for l in lines if re.match(
                    r'^(\d{1,2}\s+\w{3}|\w{3}\s+\d{1,2}|\d{1,2}\s+\w+\s*[-–])', l
                )]

                title = title.strip()
                # Clean up " Takvimi" suffix common on biletzero
                title = re.sub(r'\s+(Etkinlik\s+)?Takvimi$', '', title, flags=re.IGNORECASE).strip()

                if not title or len(title) < 5:
                    continue
                # Skip category header links
                if title in CATEGORY_MAP.values() or title.lower() in CATEGORY_MAP:
                    continue
                # Skip if title looks like a date or city
                if re.match(r'^(istanbul|ankara|izmir|bursa|antalya|\d{1,2}\s+\w{3})$', title.lower()):
                    continue

                # Try to get date from nearby elements
                date_text = None
                try:
                    # Look for date in parent card
                    card = await link.evaluate_handle(
                        'el => el.closest("[class*=card], [class*=event], [class*=item], article, li") || el.parentElement'
                    )
                    if card:
                        card_el = card.as_element()
                        if card_el:
                            card_text = await card_el.inner_text()
                            # Try to extract date pattern
                            date_match = re.search(
                                r'(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})',
                                card_text
                            )
                            if date_match:
                                date_text = date_match.group(0)
                except Exception:
                    pass

                # Try image
                image_url = None
                try:
                    img = await page.query_selector(f'img[src*="{parts[-1][:10]}"]')
                    if img:
                        image_url = await img.get_attribute('src')
                except Exception:
                    pass

                category, external_id = parse_category_and_id(path)
                raw_items.append({
                    'title': title,
                    'url': full_url,
                    'date_text': date_text,
                    'image_url': image_url,
                    'category': category,
                    'external_id': external_id,
                })

            logger.info(f"Found {len(raw_items)} events on list page for {city_slug}")

            # Fetch detail pages for first 50 events
            detail_limit = min(50, len(raw_items))
            for i, item in enumerate(raw_items[:detail_limit]):
                venue_name = None
                venue_city = city.capitalize() if city else None
                price_min = None
                price_max = None
                description = None
                start_date = item.get('date_text')
                image_url = item.get('image_url')

                try:
                    detail_page = await context.new_page()
                    await detail_page.goto(item['url'], wait_until='networkidle', timeout=20000)

                    # Extract venue
                    venue_selectors = [
                        '[class*=venue]', '[class*=location]', '[class*=mekan]',
                        '[itemprop=location]', '[class*=place]'
                    ]
                    for sel in venue_selectors:
                        el = await detail_page.query_selector(sel)
                        if el:
                            venue_name = (await el.inner_text()).strip().split('\n')[0]
                            break

                    # Extract price
                    price_selectors = [
                        '[class*=price]', '[class*=fiyat]', '[class*=ticket]',
                        '[class*=bilet]'
                    ]
                    for sel in price_selectors:
                        el = await detail_page.query_selector(sel)
                        if el:
                            price_text = (await el.inner_text()).strip()
                            price_min, price_max = parse_price(price_text)
                            if price_min:
                                break

                    # Extract description
                    desc_selectors = [
                        '[class*=description]', '[class*=aciklama]', '[class*=content]',
                        'article p', '[itemprop=description]'
                    ]
                    for sel in desc_selectors:
                        el = await detail_page.query_selector(sel)
                        if el:
                            description = (await el.inner_text()).strip()[:500]
                            if description:
                                break

                    # Extract image if not found
                    if not image_url:
                        img = await detail_page.query_selector('meta[property="og:image"]')
                        if img:
                            image_url = await img.get_attribute('content')

                    # Extract date if not found
                    if not start_date:
                        date_selectors = ['[class*=date]', '[class*=tarih]', 'time']
                        for sel in date_selectors:
                            el = await detail_page.query_selector(sel)
                            if el:
                                dt = await el.get_attribute('datetime')
                                if dt:
                                    start_date = dt
                                    break
                                text = (await el.inner_text()).strip()
                                if text:
                                    start_date = text
                                    break

                    await detail_page.close()
                    logger.info(f"[{i+1}/{detail_limit}] Detail fetched: {item['title'][:40]}")

                except Exception as e:
                    logger.warning(f"Error fetching detail for {item['url']}: {e}")
                    try:
                        await detail_page.close()
                    except Exception:
                        pass

                events.append(RawEvent(
                    source_id=self.source_id,
                    external_id=item['external_id'],
                    title=item['title'],
                    category=item['category'],
                    start_date=start_date,
                    end_date=None,
                    venue_name=venue_name,
                    venue_city=venue_city or 'Türkiye',
                    price_min=price_min,
                    price_max=price_max,
                    image_url=image_url,
                    ticket_url=item['url'],
                    description=description,
                ))

            # For events beyond detail_limit, add with minimal info
            for item in raw_items[detail_limit:]:
                category, external_id = item['category'], item['external_id']
                events.append(RawEvent(
                    source_id=self.source_id,
                    external_id=external_id,
                    title=item['title'],
                    category=category,
                    start_date=item.get('date_text'),
                    end_date=None,
                    venue_name=None,
                    venue_city=city.capitalize() if city else 'Türkiye',
                    price_min=None,
                    price_max=None,
                    image_url=item.get('image_url'),
                    ticket_url=item['url'],
                    description=None,
                ))

            await browser.close()

        return events
