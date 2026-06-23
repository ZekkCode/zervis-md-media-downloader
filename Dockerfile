FROM python:3.12-slim

# Install system dependencies (ffmpeg is required by yt-dlp for video/audio merging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY scripts/ ./scripts/
COPY cookies/ ./cookies/
COPY downloads/ ./downloads/
COPY logs/ ./logs/

# Expose port for FastAPI worker
EXPOSE 3000

# Set python path to allow imports of scripts package
ENV PYTHONPATH=/app

# Default command runs the worker (can be overridden)
CMD ["python", "scripts/worker.py"]
