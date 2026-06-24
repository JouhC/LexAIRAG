from sentence_transformers import SentenceTransformer
from psycopg import sql, rows
from pgvector.psycopg import register_vector 
from pipeline.db_init import create_connection, close_connection
import time

def search_chunks(conn, model, query: str, k: int = 5):
    # 1. Encode query to a numpy array
    t0 = time.perf_counter()
    q_vec = model.encode([f"query: {query}"], normalize_embeddings=True)[0]
    t1 = time.perf_counter()

    sql = """
        SELECT
            id,
            case_no,
            section,
            chunk_index,
            text,
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
    
    t2 = time.perf_counter()

    # Optional: convert distance → similarity for humans
    for r in rows_:
        d = float(r["distance"])    # cosine distance in [0, 2]
        r["similarity"] = 1 - d / 2 # approx in [0, 1]
    t3 = time.perf_counter()

    print(f"Embed time: {(t1 - t0) * 1000:.1f} ms")
    print(f"DB time (Python-side): {(t2 - t1) * 1000:.1f} ms")
    print(f"Conversion time (Python-side): {(t3 - t2) * 1000:.1f} ms")
    print(f"Total backend time: {(t3 - t0) * 1000:.1f} ms")

    return rows_

def main():
    MODEL = SentenceTransformer("BAAI/bge-m3")

    conn = create_connection()
    register_vector(conn)
    hits = search_chunks(conn, MODEL, "child abuse",1)
    for h in hits:
        print(h["case_no"], h["section"], h["chunk_index"], "similarity:", h["similarity"], h["preview"])
    close_connection(conn)

if __name__ == "__main__":
    main()