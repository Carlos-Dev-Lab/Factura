# Fijada por digest: un rebuild usa exactamente la misma base. Dependabot propone las actualizaciones.
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract OCR (español + inglés) para leer fotos y PDFs escaneados
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
# pip actualizado: las versiones viejas tienen CVEs al instalar paquetes.
# Con --require-hashes se instala exactamente lo del lock: un paquete alterado o una versión
# distinta de cualquier dependencia (también las indirectas) hace fallar la construcción.
RUN pip install --upgrade "pip==26.2.2" && pip install --require-hashes --no-deps -r requirements.txt && pip check

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN useradd --uid 10001 --create-home factura \
 && mkdir -p /data/uploads && chown -R factura /data
USER factura

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

# Aplica migraciones pendientes y arranca la API.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-server-header --timeout-keep-alive 30 --workers ${WEB_CONCURRENCY:-2}"]
