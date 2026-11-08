# Use the official uv image with Python 3.12 (Debian Bookworm slim)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Enable bytecode compilation and use copy instead of hardlinks for containers
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Step 1: Install dependencies first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Step 2: Copy application source
COPY src ./src
COPY README.md pyproject.toml ./

# Step 3: Install the project itself (without dev dependencies)
RUN uv sync --frozen --no-dev

# Place virtual environment binaries directly in PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Run using FastAPI CLI in production mode (defaults to 0.0.0.0:8000)
CMD ["fastapi", "run"]
