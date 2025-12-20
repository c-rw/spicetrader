FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY src/ ./src/

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data

# Run as non-root user
RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

USER appuser

# Run the multi-coin bot by default
CMD ["python", "-m", "src.multi_coin_bot"]
