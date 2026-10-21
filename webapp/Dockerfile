FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY app ./app
COPY static ./static
COPY content ./content
ENV ARTIFACTS_DIR=/data/artifacts LIVE_DIR=/data/live SEED_PRICE_TSV=/data/artifacts/coin_metrics.tsv RUN_SCHEDULER=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
