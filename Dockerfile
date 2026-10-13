# Imágenes de Python para docker-compose.yml:
#   api       la API con lo mismo que instala Vercel (requirements.txt) y uvicorn
#   pipeline  añade pandas, LightGBM y Alembic para migraciones, ingesta y entrenamiento

FROM python:3.12-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --create-home app

COPY requirements.txt ./
RUN pip install -r requirements.txt "uvicorn[standard]>=0.30"

COPY src ./src

USER app
EXPOSE 8000
# Detrás de nginx: confía en su X-Forwarded-For para conocer la IP del cliente
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]


FROM api AS pipeline

USER root
# LightGBM necesita OpenMP
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-pipeline.txt ./
RUN pip install -r requirements-pipeline.txt

COPY alembic.ini ./
COPY alembic ./alembic

USER app
CMD ["python", "-m", "src.pipeline", "daily"]
