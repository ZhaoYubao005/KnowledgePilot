FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KP_DATA_DIR=/app/data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown app:app /app/data
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "knowledge_pilot.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
