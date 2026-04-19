#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# CVIS v9 — HTTPS Setup
# Run as root on your EC2 / VPS.
#
# PATH A — Cloudflare (recommended, 5 minutes):
#   bash https-setup.sh cloudflare
#
# PATH B — Let's Encrypt / certbot (self-hosted):
#   bash https-setup.sh letsencrypt yourdomain.com ops@yourdomain.com
# ─────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."     # run from repo root

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

MODE="${1:-}"
DOMAIN="${2:-${DOMAIN:-}}"
EMAIL="${3:-${ACME_EMAIL:-}}"

# ─────────────────────────────────────────────────────────
# PATH A — CLOUDFLARE PROXY
# ─────────────────────────────────────────────────────────
# How it works:
#   1. Your DNS A record points to your server IP via Cloudflare (orange cloud ☁️)
#   2. Cloudflare terminates TLS at the edge — free, automatic, no certbot needed
#   3. Traffic between Cloudflare → your nginx can be HTTP on port 80 (Full mode)
#      OR end-to-end encrypted with a Cloudflare Origin Certificate (Full Strict)
#
# nginx config needed: only a plain HTTP server block (Cloudflare adds HTTPS at edge)
# OR install a Cloudflare Origin Certificate for Full Strict mode (recommended)

setup_cloudflare() {
    info "Setting up Cloudflare Origin Certificate (Full Strict TLS)"
    info ""
    info "Step 1 — In Cloudflare dashboard:"
    info "  SSL/TLS → Origin Server → Create Certificate"
    info "  Choose RSA, 15 years, add your domain + *.yourdomain.com"
    info "  Download: origin.pem (certificate) + origin.key (private key)"
    info ""
    info "Step 2 — Copy the cert files to this server:"
    info "  scp origin.pem user@yourserver:/opt/cvis/nginx/certs/cloudflare.crt"
    info "  scp origin.key user@yourserver:/opt/cvis/nginx/certs/cloudflare.key"
    info ""
    info "Step 3 — Update nginx.conf to use the origin cert:"

    # Patch nginx.conf to use Cloudflare Origin Certificate
    if grep -q 'letsencrypt' nginx/nginx.conf; then
        DOMAIN_IN_CONF=$(grep 'server_name ' nginx/nginx.conf | head -1 | awk '{print $2}' | tr -d ';')
        sed -i \
            -e "s|/etc/letsencrypt/live/.*/fullchain.pem|/etc/nginx/certs/cloudflare.crt|g" \
            -e "s|/etc/letsencrypt/live/.*/privkey.pem|/etc/nginx/certs/cloudflare.key|g" \
            -e "s|ssl_trusted_certificate.*|# ssl_trusted_certificate not needed for Cloudflare origin cert|g" \
            nginx/nginx.conf
        ok "nginx.conf patched for Cloudflare Origin Certificate"
    fi

    info ""
    info "Step 4 — Update your .env:"
    info "  DOMAIN=yourdomain.com"
    info ""
    info "Step 5 — Restart nginx:"
    info "  docker compose up -d --no-deps frontend"
    info ""
    info "Step 6 — In Cloudflare dashboard → SSL/TLS → set to 'Full (strict)'"
    info ""
    ok "Cloudflare setup complete. Your origin is protected."
    echo ""
    warn "Cloudflare handles certificate renewal automatically — no cron needed."
}

# ─────────────────────────────────────────────────────────
# PATH B — LET'S ENCRYPT / CERTBOT
# ─────────────────────────────────────────────────────────
setup_letsencrypt() {
    [[ -z "$DOMAIN" ]] && die "Usage: $0 letsencrypt <domain> <email>"
    [[ -z "$EMAIL"  ]] && die "Usage: $0 letsencrypt <domain> <email>"

    info "Let's Encrypt setup for: $DOMAIN (contact: $EMAIL)"

    # ── 1. Verify ports 80 + 443 are reachable ────────────
    info "Checking port 80 is accessible from the internet..."
    if command -v curl &>/dev/null; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "http://$DOMAIN/nginx-health" || true)
        if [[ "$HTTP_CODE" == "200" ]]; then
            ok "Port 80 is reachable (nginx responding)"
        else
            warn "Port 80 check returned $HTTP_CODE — certbot may fail if port is blocked"
            warn "Check: security groups / firewall allow 0.0.0.0:80 and 0.0.0.0:443"
        fi
    fi

    # ── 2. Update .env with domain ────────────────────────
    if [[ -f .env ]]; then
        if grep -q '^DOMAIN=' .env; then
            sed -i "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" .env
        else
            echo "DOMAIN=$DOMAIN" >> .env
        fi
        if grep -q '^ACME_EMAIL=' .env; then
            sed -i "s|^ACME_EMAIL=.*|ACME_EMAIL=$EMAIL|" .env
        else
            echo "ACME_EMAIL=$EMAIL" >> .env
        fi
        ok ".env updated: DOMAIN=$DOMAIN"
    else
        warn ".env not found — create it from .env.example first"
    fi

    # ── 3. Patch nginx.conf with real domain ──────────────
    sed -i "s/CVIS_DOMAIN_PLACEHOLDER/$DOMAIN/g" nginx/nginx.conf
    ok "nginx.conf: domain set to $DOMAIN"

    # ── 4. Start nginx (HTTP only) so ACME challenge works ─
    info "Starting nginx on port 80 for ACME webroot challenge..."
    docker compose up -d frontend
    sleep 3

    # ── 5. Run certbot to obtain certificate ──────────────
    info "Running certbot webroot challenge for $DOMAIN..."
    docker compose run --rm certbot certonly \
        --webroot \
        --webroot-path /var/www/certbot \
        --domain "$DOMAIN" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive
    ok "Certificate obtained: /etc/letsencrypt/live/$DOMAIN/"

    # ── 6. Reload nginx with full TLS ─────────────────────
    info "Reloading nginx with TLS enabled..."
    docker compose restart frontend
    sleep 2

    # ── 7. Smoke test ────────────────────────────────────
    info "Testing HTTPS..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "https://$DOMAIN/health" || echo "000")
    if [[ "$HTTP_CODE" == "200" ]]; then
        ok "HTTPS is working: https://$DOMAIN"
    else
        warn "HTTPS returned $HTTP_CODE — check docker compose logs frontend"
    fi

    ok "Let's Encrypt setup complete."
    echo ""
    info "Certificate auto-renews every 12h via the certbot container."
    info "Check renewal status: docker compose logs certbot"

    # ── 8. Test renewal (dry-run) ─────────────────────────
    info "Running renewal dry-run to confirm cron will work..."
    docker compose run --rm certbot renew --dry-run \
        && ok "Renewal dry-run passed" \
        || warn "Renewal dry-run failed — check certbot logs"
}

# ─────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────
case "$MODE" in
    cloudflare)     setup_cloudflare ;;
    letsencrypt|le) setup_letsencrypt ;;
    *)
        echo ""
        echo "  Usage:"
        echo "    bash scripts/https-setup.sh cloudflare"
        echo "    bash scripts/https-setup.sh letsencrypt yourdomain.com ops@you.com"
        echo ""
        echo "  PATH A — Cloudflare:   Fastest. TLS at edge. No certbot. Zero renewal work."
        echo "  PATH B — Let's Encrypt: Self-hosted. Port 80/443 must be open. Autorenewal via cron."
        echo ""
        exit 1
        ;;
esac
