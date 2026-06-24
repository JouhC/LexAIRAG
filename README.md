# LexAIRAG (PhilLexRAG)

LexAIRAG, also documented here as PhilLexRAG, is a retrieval-augmented search project for Philippine legal decisions. It scrapes Supreme Court decision text, chunks decisions into legal sections, embeds the chunks with `BAAI/bge-m3`, stores them in PostgreSQL with `pgvector`, and exposes semantic search through FastAPI and Streamlit.

## What It Does

- Crawls Philippine Supreme Court decision pages from the eLibrary.
- Extracts decision text and basic metadata such as case number, division, title, year, month, and source URL.
- Splits decisions into sections such as `FACTS`, `ISSUES`, `RULING`, `WHEREFORE`, or `FULL_TEXT`.
- Builds overlapping sentence chunks for retrieval.
- Stores decisions and chunks in PostgreSQL.
- Generates 1024-dimensional BGE-M3 embeddings for each chunk.
- Performs cosine-similarity vector search through `pgvector`.
- Provides both an API service and Streamlit search interfaces.

## Project Structure

```text
.
├── api/main.py                 # FastAPI search service
├── main.py                     # Batch chunking/vectorization entry point
├── streamlit_app_prod.py       # Streamlit UI that calls the API
├── streamlit_app_dev.py        # Streamlit UI that searches directly against the DB
├── config.py                   # Environment-based settings
├── pipeline/
│   ├── scraper.py              # eLibrary crawling and JSONL export
│   ├── chunking.py             # Metadata extraction, sectioning, and chunking
│   ├── db_init.py              # PostgreSQL/pgvector schema setup
│   ├── upsert.py               # Decision and chunk inserts
│   ├── vectorize.py            # Embedding/token utilities
│   ├── similarity_search.py    # Vector search query logic
│   └── preprocessing.py        # Text preprocessing helpers
├── data/                       # Local scraped/processed data
├── notebooks/                  # Exploration and scraper notebooks
├── tests/                      # Database tests
└── Dockerfile                  # API container
```

## Requirements

- Python 3.13+
- PostgreSQL with the `pgvector` extension enabled
- `uv` for dependency management
- A database reachable from the application environment

The project uses `pydantic-settings`, so local configuration is loaded from `.env`.

## Environment Variables

Create a `.env` file in the project root:

```env
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=your_host
DB_PORT=5432
DEFAULT_API_URL=http://localhost:8000
```

`DEFAULT_API_URL` is used by `streamlit_app_prod.py` to call the FastAPI backend.

## Setup

Install dependencies:

```bash
uv sync
```

Initialize the database tables, indexes, triggers, and uniqueness constraints:

```bash
uv run python -m pipeline.db_init
```

This creates:

- `decisions`
- `decision_chunks`
- an IVFFlat cosine index on `decision_chunks.embedding`
- helper indexes for case number and chunk ordering

## Data Pipeline

### 1. Scrape Decisions

The scraper is designed to crawl eLibrary decision pages and write records as JSONL. Each row includes:

- `year`
- `month`
- `title`
- `url`
- `text`

The expected cleaned dataset path used by `main.py` is:

```text
data/sc_decisions_cleaned.jsonl
```

The scraper also supports local caching and checkpointing so repeated runs can resume previously processed URLs.

### 2. Chunk and Upsert

`main.py` contains the chunking/upsert flow:

```python
chunking_and_upsert(conn)
```

This reads `data/sc_decisions_cleaned.jsonl`, extracts case metadata, splits each decision into sections, builds sentence chunks, and inserts them into PostgreSQL.

### 3. Generate Embeddings

`main.py` also contains the vectorization flow:

```python
vectorize_and_upsert(conn, model, tokenizer)
```

It finds chunks where `embedding IS NULL`, embeds them with `BAAI/bge-m3`, counts tokens, and updates `decision_chunks`.

Run the batch entry point:

```bash
uv run python main.py
```

By default, `main.py` currently runs vectorization. Uncomment the `chunking_and_upsert(conn)` call if you need to load chunks first.

## Run the API

Start the FastAPI service:

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Search endpoint:

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "liability of carrier for loss of goods", "k": 5}'
```

Example response shape:

```json
{
  "results": [
    {
      "id": 1,
      "case_no": "G.R. No. 123456",
      "section": "RULING",
      "chunk_index": 0,
      "preview": "Decision text...",
      "distance": 0.24,
      "similarity": 0.88
    }
  ]
}
```

## Run the Streamlit UI

Production-style UI that calls the FastAPI service:

```bash
uv run streamlit run streamlit_app_prod.py
```

Development UI that connects directly to PostgreSQL:

```bash
uv run streamlit run streamlit_app_dev.py
```

## Docker

Build the API image:

```bash
docker build -t phillexrag-api .
```

Run it:

```bash
docker run --env-file .env -p 8000:8000 phillexrag-api
```

The container starts:

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Notes

- Embeddings use `BAAI/bge-m3`, which produces 1024-dimensional vectors. The database schema expects `VECTOR(1024)`.
- Query text is embedded with the prefix `query: ` before similarity search.
- Cosine distance is converted to an approximate similarity score with `1 - distance / 2`.
- The database schema expects the `pgvector` extension to be available before vector indexes can be created.
- Scraping should be run responsibly with delays and checkpointing enabled.

## Portfolio Note

LexAIRAG is featured in my portfolio as a legal RAG system that connects web scraping, legal-text chunking, vector search, FastAPI, PostgreSQL, and Streamlit into one applied AI workflow.
