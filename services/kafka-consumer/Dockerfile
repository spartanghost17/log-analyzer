#FROM python:3.11-slim
#
#WORKDIR /app
#
## Install curl for health checks
#RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
#
## Install Python dependencies
#COPY requirements.txt .
#RUN pip install --no-cache-dir -r requirements.txt
#
## Copy application
#COPY app.py .
#
## Expose API port
#EXPOSE 8001
#
## Run the FastAPI application
#CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY /src ./src

# Tell Python where code lives
ENV PYTHONPATH=/app/src

EXPOSE 8001

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]