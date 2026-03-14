FROM python:3.13-slim

LABEL maintainer="A_OpenClaw"
LABEL description="A_OpenClaw — Personal AI Assistant"

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt logger_pkg-0.1.0-py3-none-any.whl ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY core/ core/
COPY adapters/ adapters/
COPY heartbeat/ heartbeat/
COPY skills/ skills/
COPY main.py ./

# Copy default config and memory templates
COPY config/ config/
COPY memory/ memory/

# Create directories for runtime data
RUN mkdir -p logs memory/logs custom_skills

# Default command — interactive CLI mode
CMD ["python", "main.py"]
