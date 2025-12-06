FROM python:3.11-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .

# Expose API port
EXPOSE 8002

# Run the FastAPI application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]