FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    ffmpeg libsndfile1 git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv .venvF5

ENV PATH="/app/.venvF5/bin:$PATH"

COPY requirementsF5.txt . 

RUN pip install --no-cache-dir -r requirementsF5.txt --extra-index-url https://download.pytorch.org/whl/cu118

COPY . .

EXPOSE 8001

CMD ["python", "F5TTS.py"]