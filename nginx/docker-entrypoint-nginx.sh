#!/bin/sh
# CVIS v9 — nginx startup script (FIXED: no template dependency)

set -eu

DOMAIN="${DOMAIN:-localhost}"
LE_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
SELFSIGNED_KEY="/etc/nginx/certs/selfsigned.key"
SELFSIGNED_CRT="/etc/nginx/certs/selfsigned.crt"

echo "[cvis-nginx] Domain: ${DOMAIN}"

# ── TLS certificate handling ─────────────────────────────
if [ -f "${LE_CERT}" ]; then
    echo "[cvis-nginx] Let's Encrypt certificate found — HTTPS enabled"
else
    echo "[cvis-nginx] No LE cert — generating self-signed cert"
    mkdir -p /etc/nginx/certs

    if [ ! -f "${SELFSIGNED_KEY}" ]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "${SELFSIGNED_KEY}" \
            -out    "${SELFSIGNED_CRT}" \
            -subj   "/C=US/ST=Dev/L=Local/O=CVIS/CN=${DOMAIN}" \
            -addext "subjectAltName=DNS:${DOMAIN},DNS:localhost,IP:127.0.0.1" \
            2>/dev/null

        echo "[cvis-nginx] Self-signed cert created"
    fi
fi

# ── Validate config ─────────────────────────────────────
nginx -t

echo "[cvis-nginx] Starting nginx..."

# ── Start nginx ─────────────────────────────────────────
exec nginx -g "daemon off;"
