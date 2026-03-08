FROM python:3.13.5-alpine

WORKDIR /app

RUN python -m venv .venv

ENV PATH="/app/.venv/bin:$PATH"

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]