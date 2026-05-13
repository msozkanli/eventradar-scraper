def is_duplicate(conn, source: str, source_id: str) -> bool:
    """Check if event already exists using the unique (source, source_id) key."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM events WHERE source = %s AND source_id = %s",
            (source, source_id)
        )
        return cur.fetchone() is not None
