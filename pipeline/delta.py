def detect_delta(conn, source: str, source_id: str, new_price_min) -> dict | None:
    """Detect price drop for an existing event."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT price_min FROM events WHERE source = %s AND source_id = %s",
            (source, source_id)
        )
        row = cur.fetchone()
        if not row:
            return None
        old_price = row[0]
        if new_price_min and old_price and float(new_price_min) < float(old_price):
            return {'type': 'price_drop', 'old': float(old_price), 'new': float(new_price_min)}
    return None
