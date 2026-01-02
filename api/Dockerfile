FROM python:3.10-slim

WORKDIR /app

COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api/app /app/app

RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/trading.db

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
