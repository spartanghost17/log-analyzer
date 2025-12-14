FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    #ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy requirements
COPY requirements.txt .
# COPY pyproject.toml .

# Create virtual environment and install deps with uv
# RUN uv venv /app/.venv \
#     && uv add -r requirements.txt

RUN uv init . \
    && uv add -r requirements.txt

# Copy application code
COPY /src ./src

# Tell Python where code lives
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8002

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]