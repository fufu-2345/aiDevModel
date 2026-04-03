FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /app/.venvF5
ENV PATH="/app/.venvF5/bin:$PATH"
ENV BUST_CACHE=1

COPY requirementsF5.txt . 

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirementsF5.txt --extra-index-url https://download.pytorch.org/whl/cu118

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venvF5 /app/.venvF5

ENV PATH="/app/.venvF5/bin:$PATH"

COPY . .

EXPOSE 8001

CMD ["python", "F5TTS.py"]