FROM python:3.11.14-alpine

WORKDIR /app

RUN python -m venv .venvF5
ENV PATH="/app/.venvF5/bin:$PATH"

COPY requirementsF5.txt . 

RUN pip install --no-cache-dir -r requirementsF5.txt

COPY . .

EXPOSE 8100

CMD ["python", "F5TTS.py"]