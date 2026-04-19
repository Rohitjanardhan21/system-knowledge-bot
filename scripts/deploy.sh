#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# CVIS v9 — First Deploy / Update Script
# Tested on: Ubuntu 22.04 LTS (EC2 t3.small+)
#
# First run (fresh server):
#   curl -fsSL https://raw.githubusercontent.com/you/cvis/main/scripts/deploy.sh | bash
#
# Re-run to update to a new image tag:
#   bash scripts/deploy.sh update v9.1.0
# ─────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLU}[deploy]${NC}  $*"; }
ok()   { echo -e "${GRN}[  ok  ]${NC}  $*"; }
warn() { echo -e "${YLW}[ warn ]${NC}  $*"; }
die()  { echo -e "${RED}[ fail ]${NC}  $*"; exit 1; }

DEPLOY_DIR="/opt/cvis"
REPO="${CVIS_REPO:-https://github.com/you/cvis.git}"
MODE="${1:-install}"
VERSION="${2:-main}"

# ── Require root ──────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash scripts/deploy.sh"

# ─────────────────────────────────────────────────────────
# STEP 1 — System packages
# ─────────────────────────────────────────────────────────
install_deps() {
    info "Installing system dependencies..."
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        curl wget git unzip ca-certificates \
        gnupg lsb-release ufw fail2ban

    # Docker (official repo)
    if ! command -v docker &>/dev/null; then
        info "Installing Docker..."
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | gpg --dearmor -o /usr/share/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
            > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
        systemctl enable --now docker
        ok "Docker installed: $(docker --version)"
    else
        ok "Docker already installed: $(docker --version)"
    fi
}

# ─────────────────────────────────────────────────────────
# STEP 2 — Firewall
# ─────────────────────────────────────────────────────────
configure_firewall() {
    info "Configuring UFW firewall..."
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp   comment "SSH"
    ufw allow 80/tcp   comment "HTTP (→ HTTPS redirect)"
    ufw allow 443/tcp  comment "HTTPS"
    # Block direct backend access from internet (nginx proxies only)
    ufw deny 8000/tcp  comment "Block direct backend"
    ufw deny 9090/tcp  comment "Block direct Prometheus"
    ufw deny 3000/tcp  comment "Block direct Grafana"
    ufw --force enable
    ok "Firewall configured (22, 80, 443 open; 8000/9090/3000 blocked)"
}

# ─────────────────────────────────────────────────────────
# STEP 3 — fail2ban (SSH brute-force protection)
# ─────────────────────────────────────────────────────────
configure_fail2ban() {
    info "Configuring fail2ban..."
    cat > /etc/fail2ban/jail.local << 'F2B'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = /var/log/auth.log
F2B
    systemctl enable --now fail2ban
    ok "fail2ban active (SSH: 5 retries → 1h ban)"
}

# ─────────────────────────────────────────────────────────
# STEP 4 — Clone / pull repo
# ─────────────────────────────────────────────────────────
setup_repo() {
    if [[ -d "$DEPLOY_DIR/.git" ]]; then
        info "Pulling latest from $REPO..."
        cd "$DEPLOY_DIR"
        git fetch origin
        git reset --hard "origin/$VERSION" 2>/dev/null || git reset --hard "$VERSION"
        ok "Repo updated to $(git rev-parse --short HEAD)"
    else
        info "Cloning $REPO → $DEPLOY_DIR..."
        git clone --branch "$VERSION" "$REPO" "$DEPLOY_DIR"
        ok "Repo cloned"
    fi
    cd "$DEPLOY_DIR"
}

# ─────────────────────────────────────────────────────────
# STEP 5 — Generate secrets if .env missing
# ─────────────────────────────────────────────────────────
setup_env() {
    cd "$DEPLOY_DIR"
    if [[ ! -f .env ]]; then
        info "Generating fresh .env with strong secrets..."
        bash scripts/secrets-setup.sh generate
        warn "IMPORTANT: Edit .env and set DOMAIN, SMTP_*, ACME_EMAIL"
        warn "Then run: bash scripts/https-setup.sh letsencrypt <domain> <email>"
    else
        ok ".env already exists — skipping generation"
    fi
}

# ─────────────────────────────────────────────────────────
# STEP 6 — Build + start containers
# ─────────────────────────────────────────────────────────
start_services() {
    cd "$DEPLOY_DIR"
    info "Building images..."
    docker compose build --pull

    info "Starting services..."
    docker compose up -d

    info "Waiting for backend health check..."
    ATTEMPTS=0
    until docker compose exec -T backend \
        python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
        &>/dev/null || [[ $ATTEMPTS -ge 30 ]]; do
        sleep 2
        ATTEMPTS=$((ATTEMPTS+1))
        printf '.'
    done
    echo ""

    if [[ $ATTEMPTS -ge 30 ]]; then
        warn "Backend did not become healthy in 60s"
        warn "Check logs: docker compose logs backend"
    else
        ok "Backend healthy"
    fi
}

# ─────────────────────────────────────────────────────────
# STEP 7 — Smoke tests
# ─────────────────────────────────────────────────────────
smoke_test() {
    cd "$DEPLOY_DIR"
    API_KEY=$(grep '^CVIS_API_KEY=' .env | cut -d= -f2-)
    info "Running smoke tests..."

    local fails=0

    # Health (public)
    STATUS=$(curl -sf http://localhost:8000/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','fail'))" 2>/dev/null || echo "fail")
    [[ "$STATUS" == "ok" ]] && ok "/health → ok" || { warn "/health FAILED"; fails=$((fails+1)); }

    # Authenticated endpoint
    ML_STATUS=$(curl -sf -H "X-API-Key: $API_KEY" http://localhost:8000/ml/status 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('backend','fail'))" 2>/dev/null || echo "fail")
    [[ "$ML_STATUS" != "fail" ]] && ok "/ml/status → $ML_STATUS" || { warn "/ml/status FAILED (auth?)"; fails=$((fails+1)); }

    # nginx on port 80
    HTTP=$(curl -so /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
    [[ "$HTTP" =~ ^(200|301|302)$ ]] && ok "nginx port 80 → $HTTP" || { warn "nginx port 80 FAILED ($HTTP)"; fails=$((fails+1)); }

    if [[ $fails -eq 0 ]]; then
        ok "All smoke tests passed"
    else
        warn "$fails smoke test(s) failed — check docker compose logs"
    fi
}

# ─────────────────────────────────────────────────────────
# STEP 8 — Print summary
# ─────────────────────────────────────────────────────────
print_summary() {
    cd "$DEPLOY_DIR"
    DOMAIN=$(grep '^DOMAIN=' .env 2>/dev/null | cut -d= -f2- || echo "localhost")
    API_KEY=$(grep '^CVIS_API_KEY=' .env | cut -d= -f2- | head -c 12)
    echo ""
    echo -e "  ${GRN}${BOLD}CVIS v9 is running${NC}"
    echo ""
    echo -e "  Frontend : http://${DOMAIN}  (run https-setup.sh for HTTPS)"
    echo -e "  API docs : http://${DOMAIN}/docs"
    echo -e "  Health   : curl http://localhost:8000/health"
    echo -e "  Monitor  : bash scripts/monitor.sh"
    echo ""
    echo -e "  API Key  : ${API_KEY}… (see .env for full key)"
    echo ""
    echo -e "  Next steps:"
    echo -e "    1. Set DOMAIN in .env"
    echo -e "    2. bash scripts/https-setup.sh letsencrypt <domain> <email>"
    echo -e "    3. bash scripts/monitor.sh"
    echo ""
}

# ─────────────────────────────────────────────────────────
# UPDATE MODE — pull new image tag, rolling restart
# ─────────────────────────────────────────────────────────
cmd_update() {
    cd "$DEPLOY_DIR"
    info "Updating to version: $VERSION"
    setup_repo
    docker compose pull backend
    docker compose up -d --no-deps --wait backend
    smoke_test
    ok "Update complete → $VERSION"
}

# ─────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────
BOLD='\033[1m'
case "$MODE" in
    install|"")
        install_deps
        configure_firewall
        configure_fail2ban
        setup_repo
        setup_env
        start_services
        smoke_test
        print_summary
        ;;
    update)
        cmd_update
        ;;
    *)
        echo "Usage: bash deploy.sh [install|update] [version]"
        exit 1
        ;;
esac
