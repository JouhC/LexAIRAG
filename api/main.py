from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from pgvector.psycopg import register_vector

from pipeline.db_init import create_connection, close_connection
from pipeline.similarity_search import search_chunks  # adjust if needed


class SearchRequest(BaseModel):
    query: str
    k: int = 5


class ChunkResult(BaseModel):
    id: int
    case_no: Optional[str]
    section: Optional[str]
    chunk_index: int
    preview: str
    distance: float
    similarity: float


class SearchResponse(BaseModel):
    results: List[ChunkResult]


app = FastAPI(title="LexAI Vector Search API")


@app.on_event("startup")
def on_startup():
    model = SentenceTransformer("BAAI/bge-m3")

    conn = create_connection()
    if conn is None:
        # fail fast, don't allow app to start
        raise RuntimeError("Could not connect to Postgres")
    register_vector(conn)

    app.state.model = model
    app.state.conn = conn


@app.on_event("shutdown")
def on_shutdown():
    conn = getattr(app.state, "conn", None)
    if conn is not None:
        close_connection(conn)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    query = req.query.strip()
    if not query:
        # Never return None: always raise or return a proper model
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        rows_ = search_chunks(
            conn=app.state.conn,
            model=app.state.model,
            query=query,
            k=req.k,
        )
    except Exception as e:
        # Still don’t return None; raise an HTTPException
        raise HTTPException(status_code=500, detail=f"Search error: {e}")

    # If search_chunks for some reason returns None, normalize it
    if rows_ is None:
        rows_ = []

    results = [
        ChunkResult(
            id=row["id"],
            case_no=row.get("case_no"),
            section=row.get("section"),
            chunk_index=row["chunk_index"],
            preview=row["text"],
            distance=float(row["distance"]),
            similarity=float(row["similarity"]),
        )
        for row in rows_
    ]

    # Always return a SearchResponse, even if results is empty.
    return SearchResponse(results=results)
