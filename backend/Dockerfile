FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . \
    && groupadd --gid 10001 gravitywars \
    && useradd --uid 10001 --gid gravitywars --no-create-home gravitywars \
    && mkdir -p /data \
    && chown gravitywars:gravitywars /data \
    && chmod 0700 /data

USER gravitywars
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
