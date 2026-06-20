# Use Python 3.14 as per project standards
FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies for Postgres and general tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    postgresql-client \
    netcat-openbsd \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies from requirements.txt
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . /app/

# Create directories for volumes
RUN mkdir -p /app/.backups /app/imports /app/logs /app/media /app/staticfiles

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Entrypoint script handles migrations/waiting
ENTRYPOINT ["/app/entrypoint.sh"]
