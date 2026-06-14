FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY gateway/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway/main.py main.py
COPY frontend /frontend
COPY gateway/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /certs
ENV PORT=8000
ENTRYPOINT ["/entrypoint.sh"]
