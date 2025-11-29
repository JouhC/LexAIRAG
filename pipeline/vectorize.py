from sentence_transformers import SentenceTransformer
from pipeline.db_init import create_connection, close_connection
import numpy as np
from transformers import AutoTokenizer

def encode_passage(text: str, model) -> np.ndarray:
    print(f"Encoding passage of length {len(text)}")
    emb = model.encode([f"passage: {text}"], normalize_embeddings=True)[0]
    return emb

def count_tokens(text: str, tokenizer) -> int:
    return len(tokenizer.encode(text))

def embed_missing_chunks(conn, model, tokenizer):
    with conn.cursor() as cur:
        cur.execute("SELECT id, text FROM decision_chunks WHERE embedding IS NULL;")
        rows = cur.fetchall()

    for row_id, txt in rows:
        print(f"Embedding chunk id {row_id}")
        try:
            emb = encode_passage(txt, model)
            tokens = count_tokens(txt, tokenizer)
            
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE decision_chunks SET embedding = %s::vector, token_count = %s WHERE id = %s;",
                    (emb.tolist(), tokens, row_id),
                )
        except Exception as e:
            print(f"Failed to embed chunk id {row_id}: {e}")

def main():
    MODEL = SentenceTransformer("BAAI/bge-m3")
    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")

    conn = create_connection()
    embed_missing_chunks(conn, MODEL, tokenizer)
    close_connection(conn)

if __name__ == "__main__":
    main()
