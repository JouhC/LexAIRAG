from pipeline.db_init import create_connection, close_connection
conn = create_connection()

with conn.cursor() as cur:
    cur.execute("SELECT * FROM decision_chunks;")
    rows = cur.fetchall()

print("Chunks with embeddings:", rows)