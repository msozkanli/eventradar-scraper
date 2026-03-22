def is_duplicate(conn, fingerprint: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM events WHERE source_fingerprint = %s", (fingerprint,))
        return cur.fetchone() is not None
