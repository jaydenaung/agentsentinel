#!/usr/bin/env bash
# Generate a self-signed TLS certificate for local/testing use.
# Replace the generated files with your organisation's CA-signed cert
# when deploying to production.
#
# Usage:
#   chmod +x nginx/generate-certs.sh
#   ./nginx/generate-certs.sh
#
# Output:
#   nginx/certs/server.crt  — certificate (PEM)
#   nginx/certs/server.key  — private key  (PEM)

set -euo pipefail

CERTS_DIR="$(cd "$(dirname "$0")/certs" && pwd)"

echo "Generating self-signed certificate in ${CERTS_DIR} ..."

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "${CERTS_DIR}/server.key" \
    -out    "${CERTS_DIR}/server.crt" \
    -subj   "/C=US/ST=State/L=City/O=AgentSentinel/OU=Security/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:agentsentinel.local,IP:127.0.0.1"

chmod 600 "${CERTS_DIR}/server.key"
chmod 644 "${CERTS_DIR}/server.crt"

echo ""
echo "Done."
echo "  Certificate : ${CERTS_DIR}/server.crt"
echo "  Private key : ${CERTS_DIR}/server.key"
echo ""
echo "To use your organisation's certificate instead, replace these two files"
echo "with your CA-signed cert and key, then restart the nginx container:"
echo "  docker compose restart nginx"
