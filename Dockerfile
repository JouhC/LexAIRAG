# Use uv's official Python 3.13 base image
FROM ghcr.io/astral-sh/uv:python3.13-bookworm

WORKDIR /app

# Optional: keep venv inside project
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# If you need system packages (psycopg build, etc.), uncomment:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     git \
#     && rm -rf /var/lib/apt/lists/*

# Copy dependency metadata first for caching
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv (from your lockfile)
RUN uv sync --frozen --no-dev

# Copy the rest of the source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Run the API via uv + uvicorn
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
