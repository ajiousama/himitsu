FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV PORT=8080
CMD ["sh","-c","gunicorn -b 0.0.0.0:${PORT:-8080} --workers 1 --threads 2 --timeout 120 app:app"]
