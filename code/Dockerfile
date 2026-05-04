# NLE-Bench Dockerfile
# Multi-stage build for reproducible benchmark execution
#
# Build:
#   docker build -t nlebench .
#
# Run with API providers (Anthropic/OpenAI):
#   docker run -it --rm \
#     -e <PROVIDER_API_KEY_ENV> \
#     -v $(pwd)/results:/app/results \
#     nlebench --provider anthropic --model claude-sonnet-4-6-2026-02-17
#
# Run with vLLM (requires vLLM server):
#   docker run -it --rm \
#     --network host \
#     -v $(pwd)/results:/app/results \
#     nlebench --provider vllm --model Qwen/Qwen3-32B

FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Builder stage: install dependencies
# ------------------------------------------------------------
FROM base AS builder

# Copy only requirements first for better caching
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install package in editable mode with all dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# ------------------------------------------------------------
# Final stage: lean runtime image
# ------------------------------------------------------------
FROM base AS runtime

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code
COPY src/ ./src/
COPY pyproject.toml README.md ./

# Install the package (no deps, already installed)
RUN pip install --no-cache-dir --no-deps -e .

# Create results directory
RUN mkdir -p /app/results

# Default command
ENTRYPOINT ["python", "-m", "nlebench"]
CMD ["--help"]

# ------------------------------------------------------------
# Labels
# ------------------------------------------------------------
LABEL org.opencontainers.image.title="NLE-Bench" \
      org.opencontainers.image.description="Non-Linear Editing Agent Benchmark" \
      org.opencontainers.image.source="anonymous-review-bundle" \
      org.opencontainers.image.version="0.4.0"
