#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# CVIS v9 — Secrets Setup
# Generates strong secrets, writes them to .env,
# and optionally loads them as Docker Swarm secrets
# (so they are never in environment variables in prod).
#
# Usage:
#   bash scripts/secrets-setup.sh generate      # write fresh .env
#   bash scripts/secrets-setup.sh docker-secrets # load to Docker secrets store
#   bash scripts/secrets-setup.sh rotate jwt     # rotate a specific secret
# ─────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()   { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn() { echo -e "${YLW}[WARN]${NC}  $*"; }
die()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ── Generate a random secret ──────────────────────────────
gen_hex()  { python3 -c "import secrets; print(secrets.token_hex(32))"; }
gen_url()  { python3 -c "import secrets; print(secrets.token_urlsafe(32))"; }
gen_pass() { python3 -c "
import secrets, string
chars = string.ascii_letters + string.digits + '!@#\$%^&*'
print(''.join(secrets.choice(chars) for _ in range(32)))
"; }

# ─────────────────────────────────────────────────────────
# COMMAND: generate — write a fresh .env with strong secrets
# ─────────────────────────────────────────────────────────
cmd_generate() {
    if [[ -f .env ]]; then
        warn ".env already exists. Backing up to .env.bak before overwriting."
        cp .env .env.bak
    fi

    info "Generating cryptographically strong secrets..."

    JWT_SECRET=$(gen_hex)
    API_KEY=$(gen_url)
    ADMIN_PASS=$(gen_pass)
    REDIS_PASS=$(gen_hex)

    cat > .env << ENVEOF
# ─────────────────────────────────────────────────────────
# CVIS v9 — Environment  (auto-generated $(date -u +%Y-%m-%dT%H:%M:%SZ))
# NEVER commit this file to git.
# ─────────────────────────────────────────────────────────

# Server
DOMAIN=yourdomain.com
ENV=prod
PORT=8000
POLL_INTERVAL_S=1
AUTOSAVE_INTERVAL_S=300
GUNICORN_WORKERS=2
LOG_LEVEL=warning

# CORS — change to your real frontend origin
ALLOWED_ORIGIN=https://yourdomain.com

# ── SECRETS — generated $(date -u +%Y-%m-%dT%H:%M:%SZ) ──────────────────────────
JWT_SECRET=${JWT_SECRET}
CVIS_API_KEY=${API_KEY}
CVIS_ADMIN_USER=admin
CVIS_ADMIN_PASS=${ADMIN_PASS}
JWT_ACCESS_TTL_S=900
JWT_REFRESH_TTL_S=604800

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=${REDIS_PASS}

# Alerting (fill in — never hardcode in code)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SMTP_FROM=
SMTP_TO=

# HTTPS
ACME_EMAIL=ops@yourdomain.com

# Monitoring
LOKI_URL=
GRAFANA_PASS=$(gen_pass)
ENVEOF

    ok ".env written with fresh secrets"
    warn "Fill in: DOMAIN, SMTP_*, ACME_EMAIL"
    echo ""
    echo "  JWT_SECRET   : ${JWT_SECRET:0:16}…  (${#JWT_SECRET} chars)"
    echo "  CVIS_API_KEY : ${API_KEY:0:12}…     (${#API_KEY} chars)"
    echo "  ADMIN_PASS   : ${ADMIN_PASS:0:8}…   (${#ADMIN_PASS} chars)"
    echo ""
    warn "These values are printed once. They are in .env — keep it safe."
}

# ─────────────────────────────────────────────────────────
# COMMAND: docker-secrets — push .env secrets into Docker
#          Swarm secret store so they are NEVER in env vars
# ─────────────────────────────────────────────────────────
cmd_docker_secrets() {
    [[ ! -f .env ]] && die ".env not found. Run: bash scripts/secrets-setup.sh generate"

    if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
        info "Initialising Docker Swarm (single-node) for secrets support..."
        docker swarm init --advertise-addr 127.0.0.1 2>/dev/null || true
    fi

    # Load each secret from .env into Docker secrets store
    source_env() {
        # Read key=value pairs, skip comments and blanks
        while IFS='=' read -r key value; do
            [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
            value="${value%%#*}"          # strip inline comments
            value="${value//\"/}"        # strip quotes
            value="${value// /}"         # strip spaces
            echo "$key=$value"
        done < .env
    }

    declare -A SECRETS=(
        [jwt_secret]="JWT_SECRET"
        [cvis_api_key]="CVIS_API_KEY"
        [cvis_admin_pass]="CVIS_ADMIN_PASS"
        [redis_password]="REDIS_PASSWORD"
        [smtp_pass]="SMTP_PASS"
    )

    # Build lookup from .env
    declare -A ENV_VALS
    while IFS='=' read -r k v; do ENV_VALS["$k"]="$v"; done < <(source_env)

    for secret_name in "${!SECRETS[@]}"; do
        env_key="${SECRETS[$secret_name]}"
        value="${ENV_VALS[$env_key]:-}"
        if [[ -z "$value" ]]; then
            warn "Skipping $secret_name — $env_key not set in .env"
            continue
        fi
        # Create or update secret
        echo -n "$value" | docker secret create "$secret_name" - 2>/dev/null \
            || echo -n "$value" | docker secret create "${secret_name}_$(date +%s)" -
        ok "Docker secret: $secret_name"
    done

    echo ""
    info "Patch docker-compose.yml to use secrets (uncomment the secrets: block):"
    echo ""
    cat << 'PATCH'
  backend:
    secrets:
      - jwt_secret
      - cvis_api_key
      - cvis_admin_pass
    environment:
      # Point to secret files instead of plain env vars
      - JWT_SECRET_FILE=/run/secrets/jwt_secret
      - CVIS_API_KEY_FILE=/run/secrets/cvis_api_key
      - CVIS_ADMIN_PASS_FILE=/run/secrets/cvis_admin_pass

secrets:
  jwt_secret:    { external: true }
  cvis_api_key:  { external: true }
  cvis_admin_pass: { external: true }
PATCH
    echo ""
    info "Then update auth.py to read from FILE path when _FILE env var is set:"
    cat << 'PYCODE'
import os
def _read_secret(env_key: str, file_env_key: str = None) -> str:
    file_path = os.environ.get(file_env_key or f"{env_key}_FILE")
    if file_path and os.path.exists(file_path):
        return open(file_path).read().strip()
    return os.environ.get(env_key, "")

JWT_SECRET       = _read_secret("JWT_SECRET")
BOOTSTRAP_API_KEY = _read_secret("CVIS_API_KEY")
PYCODE
}

# ─────────────────────────────────────────────────────────
# COMMAND: rotate — regenerate a specific secret in .env
#          and restart the backend
# ─────────────────────────────────────────────────────────
cmd_rotate() {
    TARGET="${2:-}"
    [[ -z "$TARGET" ]] && die "Usage: $0 rotate <jwt|apikey|adminpass|redis>"
    [[ ! -f .env ]] && die ".env not found"

    cp .env ".env.bak.$(date +%Y%m%d%H%M%S)"

    case "$TARGET" in
        jwt)
            NEW=$(gen_hex)
            sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${NEW}|" .env
            ok "JWT_SECRET rotated"
            warn "All existing JWT tokens are now invalid — users must re-login"
            ;;
        apikey)
            NEW=$(gen_url)
            sed -i "s|^CVIS_API_KEY=.*|CVIS_API_KEY=${NEW}|" .env
            ok "CVIS_API_KEY rotated: ${NEW:0:12}…"
            warn "Update X-API-Key in all clients/dashboards"
            ;;
        adminpass)
            NEW=$(gen_pass)
            sed -i "s|^CVIS_ADMIN_PASS=.*|CVIS_ADMIN_PASS=${NEW}|" .env
            ok "CVIS_ADMIN_PASS rotated: ${NEW:0:8}…"
            ;;
        redis)
            NEW=$(gen_hex)
            sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${NEW}|" .env
            ok "REDIS_PASSWORD rotated"
            warn "Update REDIS_URL and restart Redis + backend"
            ;;
        *) die "Unknown secret: $TARGET. Use: jwt | apikey | adminpass | redis" ;;
    esac

    info "Restarting backend to pick up new secret..."
    docker compose up -d --no-deps --wait backend \
        && ok "Backend restarted with new secret" \
        || warn "Restart failed — run: docker compose up -d backend"
}

# ─────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────
case "${1:-}" in
    generate)        cmd_generate ;;
    docker-secrets)  cmd_docker_secrets ;;
    rotate)          cmd_rotate "$@" ;;
    *)
        echo "  Usage:"
        echo "    bash scripts/secrets-setup.sh generate          # generate .env with fresh secrets"
        echo "    bash scripts/secrets-setup.sh docker-secrets    # push to Docker secrets store"
        echo "    bash scripts/secrets-setup.sh rotate jwt        # rotate JWT secret"
        echo "    bash scripts/secrets-setup.sh rotate apikey     # rotate API key"
        echo "    bash scripts/secrets-setup.sh rotate adminpass  # rotate admin password"
        echo "    bash scripts/secrets-setup.sh rotate redis      # rotate Redis password"
        exit 1
        ;;
esac
