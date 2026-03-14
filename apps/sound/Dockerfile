FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv .venvF5

ENV PATH="/app/.venvF5/bin:$PATH"

COPY requirementsF5.txt . 

RUN pip install --no-cache-dir -r requirementsF5.txt

COPY . .

EXPOSE 8100

CMD ["python", "F5TTS.py"]