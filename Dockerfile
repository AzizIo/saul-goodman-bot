# Saul Goodman ⚖️
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC

WORKDIR /app

# Непривилегированный пользователь: боту root ни к чему
RUN useradd --create-home --uid 10001 saul

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=saul:saul . .

RUN mkdir -p /app/data/qr && chown -R saul:saul /app/data

USER saul

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import sys,os; sys.exit(0 if os.path.exists(os.getenv('DB_PATH','/app/data/saul.db')) else 1)"

CMD ["python", "main.py"]