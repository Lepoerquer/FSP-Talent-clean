FROM python:3.12-slim

# Install system dependencies (build-essential, curl, DejaVu fonts with Cyrillic for the PDF profile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend:/app/assessment-bank

# Copy requirements and install Python dependencies
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend application code and peer packages
COPY backend /app/backend
COPY assessment-bank /app/assessment-bank
COPY services /app/services
COPY ml /app/ml

# Set up symlinks for seamless module discovery
RUN ln -s /app/backend/app /app/app && \
    ln -s /app/assessment-bank /assessment-bank

# Create non-root user for security compliance
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

WORKDIR /app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
