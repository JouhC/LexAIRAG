from typing import Dict

def upsert_decision_and_get_id(conn, chunk_meta: Dict) -> int:
    """
    Ensure a decisions row exists for this case_no and return its id.
    Uses division/title from the chunk for now.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO decisions (case_no, division, title)
            VALUES (%s, %s, %s)
            ON CONFLICT (case_no) DO UPDATE
                SET division = COALESCE(EXCLUDED.division, decisions.division),
                    title    = COALESCE(EXCLUDED.title, decisions.title)
            RETURNING id;
            """,
            (
                chunk_meta.get("case_no"),
                chunk_meta.get("division"),
                chunk_meta.get("title"),
            ),
        )
        decision_id = cur.fetchone()[0]
    return decision_id

def insert_chunk_safe(conn, chunk_meta: dict):
    decision_id = upsert_decision_and_get_id(conn, chunk_meta)
    with conn.cursor() as cur:
        cur.execute("""
        INSERT INTO decision_chunks (decision_id, case_no, section, chunk_index, text)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (case_no, section, chunk_index) DO NOTHING
        RETURNING id;
        """, (
            decision_id,
            chunk_meta["case_no"],
            chunk_meta.get("section"),
            chunk_meta["chunk_index"],
            chunk_meta["text"]
        ))
        res = cur.fetchone()
        return res[0] if res else None
