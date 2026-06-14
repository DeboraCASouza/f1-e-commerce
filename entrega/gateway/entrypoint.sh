#!/bin/sh
# Generate self-signed TLS certificate on first boot
if [ ! -f /certs/cert.pem ]; then
    openssl req -x509 -newkey rsa:2048 -keyout /certs/key.pem -out /certs/cert.pem \
        -days 365 -nodes \
        -subj "/C=BR/ST=SP/L=Local/O=PaddockStore/CN=gateway" \
        2>/dev/null
    echo "[gateway] TLS certificate generated."
fi
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --ssl-keyfile /certs/key.pem \
    --ssl-certfile /certs/cert.pem
