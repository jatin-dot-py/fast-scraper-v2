# Multi-stage build

# Stage 1: Build Go scraper
FROM golang:1.20-alpine AS go-builder

WORKDIR /go/src/app

# Install build dependencies
RUN apk add --no-cache git

# Copy Go source code
COPY go-scraper/ .

# Build the Go executable
RUN go mod init scraper && \
    go mod tidy && \
    go build -o go-scraper .

# Stage 2: Python FastAPI
FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Python application code
COPY app/ /app/app/

# Copy the Go executable from the go-builder stage
COPY --from=go-builder /go/src/app/go-scraper /app/go-scraper/go-scraper
RUN chmod +x /app/go-scraper/go-scraper

# Create a non-root user and switch to it
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Expose port
EXPOSE 8000