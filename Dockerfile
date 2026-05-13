FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt docker-pip-constraints.txt ./
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -c docker-pip-constraints.txt \
    -r requirements.txt

COPY app /app/app
COPY samples /app/samples
COPY tests /app/tests
COPY pytest.ini /app/pytest.ini

ENV LEGAL_WORKFLOW_DATA_DIR=/data
ENV PYTHONPATH=/app

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=8s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
