FROM python:3.12-alpine3.24

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
COPY rede-alimenta-back/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup -g 10001 -S alimenta \
    && adduser -u 10001 -S -G alimenta -H alimenta

COPY --chown=alimenta:alimenta rede-alimenta-back/ /app/rede-alimenta-back/
COPY --chown=alimenta:alimenta frontend/ /app/frontend/
USER alimenta
WORKDIR /app/rede-alimenta-back
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)"
CMD ["python", "server.py"]
