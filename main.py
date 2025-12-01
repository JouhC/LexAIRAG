from pathlib import Path
import json
from typing import Optional

from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from pipeline.chunking import build_rag_chunks
from pipeline.db_init import create_connection, close_connection
from pipeline.upsert import insert_chunk_safe
from pipeline.vectorize import encode_passage, count_tokens

DATA_PATH = Path("./data/sc_elibrary_decisions_text_combined_cleaned.jsonl")
CHECKPOINT_PATH = Path("./data/chunking_checkpoint.txt")


def load_checkpoint() -> Optional[str]:
    if not CHECKPOINT_PATH.exists():
        return None
    try:
        return CHECKPOINT_PATH.read_text().strip()
    except Exception:
        return None  # corrupted checkpoint fallback


def save_checkpoint(url: str) -> None:
    CHECKPOINT_PATH.write_text(url)


def chunking_and_upsert(conn) -> None:
    last_url = load_checkpoint()
    resume_mode = last_url is not None

    print(f"▶ Resume mode: {resume_mode} | last URL: {last_url}")

    skip = resume_mode

    with DATA_PATH.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f):
            checkpoint = True
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"⚠ JSON error at line {line_number}: {e}")
                continue

            year = str(rec.get("year", ""))
            month = str(rec.get("month", ""))
            title = rec["title"]
            url = rec["url"]
            text = rec["text"]

            # Skip until we see the last processed URL
            if skip:
                if url == last_url:
                    skip = False  # stop skipping AFTER this record
                continue

            print(f"🔹 Processing record {line_number} → {url}")

            chunks = build_rag_chunks(
                text,
                max_tokens=350,
                overlap_sentences=2,
            )

            for ch in chunks:
                try:
                    cid = insert_chunk_safe(conn, ch)
                    print("   ✅ Inserted chunk id:", cid)
                except Exception as e:
                    print("   ❌ Failed to insert chunk:", e)
                    checkpoint = False
                    break # stop processing further chunks for this record
            
            if checkpoint:
                # Save checkpoint as last processed unique URL
                save_checkpoint(url)

        print("✅ Chunking complete!")

def vectorize_and_upsert(conn, model: SentenceTransformer, tokenizer) -> None:
    """
    Fetch all chunks without embeddings, encode them, and update the table.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, text FROM decision_chunks WHERE embedding IS NULL;")
        rows = cur.fetchall()

    print(f"▶ Found {len(rows)} chunks to embed.")

    for row_id, txt in rows:
        print(f"Embedding chunk id {row_id}")
        try:
            emb = encode_passage(txt, model)
            tokens = count_tokens(txt, tokenizer)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE decision_chunks
                    SET embedding = %s::vector,
                        token_count = %s
                    WHERE id = %s;
                    """,
                    (emb.tolist(), tokens, row_id),
                )
        except Exception as e:
            print(f"❌ Failed to embed chunk id {row_id}: {e}")


def main() -> None:
    conn: Optional[object] = None

    try:
        conn = create_connection()
        if conn is None:
            print("❌ Failed to create DB connection.")
            return

        model = SentenceTransformer("BAAI/bge-m3")
        tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")

        # 1. Chunk + upsert (resumable via checkpoint)
        chunking_and_upsert(conn)

        # 2. Embed chunks that are still missing embeddings
        vectorize_and_upsert(conn, model, tokenizer)
    finally:
        if conn is not None:
            close_connection(conn)


if __name__ == "__main__":
    main()
