from sentence_transformers import SentenceTransformer
from psycopg import sql, rows
from pgvector.psycopg import register_vector 
from pipeline.db_init import create_connection, close_connection

def search_chunks(conn, model, query: str, k: int = 5):
    # 1. Encode query to a numpy array
    q_vec = model.encode([f"query: {query}"], normalize_embeddings=True)[0]

    sql = """
        SELECT
            id,
            case_no,
            section,
            chunk_index,
            substring(text for 300) AS preview,
            embedding <=> %s AS distance
        FROM decision_chunks
        WHERE embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT %s;
    """

    with conn.cursor(row_factory=rows.dict_row) as cur:
        # pgvector adapter will cast q_vec correctly to "vector"
        cur.execute(sql, (q_vec, k))
        rows_ = cur.fetchall()

    # Optional: convert distance → similarity for humans
    for r in rows_:
        d = float(r["distance"])    # cosine distance in [0, 2]
        r["similarity"] = 1 - d / 2 # approx in [0, 1]
    return rows_

def main():
    MODEL = SentenceTransformer("BAAI/bge-m3")

    conn = create_connection()
    register_vector(conn)
    hits = search_chunks(conn, MODEL, "Ano ang final ruling sa petition?",5)
    for h in hits:
        print(h["case_no"], h["section"], h["chunk_index"], "similarity:", h["similarity"])
    close_connection(conn)