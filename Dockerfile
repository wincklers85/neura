FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/var/data

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN mkdir -p /var/data

EXPOSE 10000

# Usa sh esplicitamente: funziona anche se Git perde il flag eseguibile.
CMD ["sh", "-c", "mkdir -p \"${DATA_DIR:-/var/data}\" && exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --workers ${WEB_WORKERS:-1} --proxy-headers --forwarded-allow-ips='*'"]
