def detect_delta(conn, fingerprint: str, new_price_min: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT price_min FROM events WHERE source_fingerprint = %s", (fingerprint,))
        row = cur.fetchone()
        if not row:
            return None
        old_price = row[0]
        if new_price_min and old_price and new_price_min < old_price:
            return {'type': 'price_drop', 'old': old_price, 'new': new_price_min}
    return None
