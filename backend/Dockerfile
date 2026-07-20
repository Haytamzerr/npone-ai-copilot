# ---- N+ONE AI Copilot backend image ----
FROM python:3.11-slim

# System deps needed by unstructured/pypdf/faiss at build time
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p vectorstore logs database

EXPOSE 8000

# Non-root user for defense in depth
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
