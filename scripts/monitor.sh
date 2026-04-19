#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# CVIS v9 — Terminal Monitor
# A single command that shows everything at once.
#
# Usage:
#   bash scripts/monitor.sh           # live dashboard (default)
#   bash scripts/monitor.sh logs      # follow all service logs
#   bash scripts/monitor.sh stats     # docker stats loop
#   bash scripts/monitor.sh health    # one-shot health check
#   bash scripts/monitor.sh alerts    # recent fired alerts
# ─────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'
CYN='\033[0;36m'; WHT='\033[1;37m'; DIM='\033[2m'; NC='\033[0m'
BOLD='\033[1m'

API="${CVIS_API_URL:-http://localhost:8000}"
API_KEY="${CVIS_API_KEY:-$(grep '^CVIS_API_KEY=' .env 2>/dev/null | cut -d= -f2-)}"

# ── Helpers ───────────────────────────────────────────────
api_get() {
    curl -sf -H "X-API-Key: $API_KEY" "${API}${1}" 2>/dev/null || echo "{}"
}
color_pct() {
    local v="$1"
    local n="${v//[^0-9.]/}"
    if (( $(echo "$n > 80" | bc -l 2>/dev/null || echo 0) )); then echo -e "${RED}${v}${NC}"
    elif (( $(echo "$n > 60" | bc -l 2>/dev/null || echo 0) )); then echo -e "${YLW}${v}${NC}"
    else echo -e "${GRN}${v}${NC}"; fi
}
bar() {
    local pct="${1//[^0-9.]/}"
    local width=20
    local filled=$(printf "%.0f" "$(echo "$pct * $width / 100" | bc -l 2>/dev/null || echo 0)")
    local empty=$((width - filled))
    printf "${BLU}[${NC}"
    printf '%0.s█' $(seq 1 $filled 2>/dev/null) 2>/dev/null
    printf '%0.s░' $(seq 1 $empty  2>/dev/null) 2>/dev/null
    printf "${BLU}]${NC}"
}

# ─────────────────────────────────────────────────────────
# DASHBOARD MODE  (default — refreshes every 3 seconds)
# ─────────────────────────────────────────────────────────
cmd_dashboard() {
    while true; do
        clear
        echo -e "${CYN}${BOLD}◈ CVIS v9 — Live Monitor${NC}  ${DIM}$(date '+%Y-%m-%d %H:%M:%S')${NC}"
        echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"

        # ── Docker container status ────────────────────────
        echo -e "\n${WHT}CONTAINERS${NC}"
        printf "  %-20s %-10s %-15s %-12s %s\n" "NAME" "STATUS" "CPU" "MEM" "RESTARTS"
        docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        c = json.loads(line.strip())
        name    = c.get('Name','?')[:18]
        status  = c.get('Status','?')
        health  = c.get('Health','')
        icon    = '✅' if 'running' in status.lower() else '❌'
        print(f'  {icon} {name:<18} {status:<12}')
    except: pass
" 2>/dev/null || echo "  (docker compose ps unavailable)"

        # ── Docker stats (non-blocking) ───────────────────
        echo ""
        docker stats --no-stream --format \
            "  {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}" \
            2>/dev/null | awk 'NR==1{printf "  %-22s %-8s %-20s %-8s %s\n","CONTAINER","CPU%","MEM","MEM%","NET I/O"} NR>1{printf "  %-22s %-8s %-20s %-8s %s\n",$1,$2,$3" "$4" "$5,$6,$7}' \
            || echo "  (docker stats unavailable)"

        # ── Backend health ─────────────────────────────────
        echo -e "\n${WHT}BACKEND HEALTH${NC}"
        HEALTH=$(api_get /health)
        if [[ "$HEALTH" == "{}" ]]; then
            echo -e "  ${RED}✗ Backend unreachable${NC}  (is docker compose up?)"
        else
            STATUS=$(echo "$HEALTH"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))")
            FITTED=$(echo "$HEALTH"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model_fitted','?'))")
            STEPS=$(echo "$HEALTH"   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('steps_lstm',0)+d.get('steps_vae',0))")
            BUFFER=$(echo "$HEALTH"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('buffer',0))")
            REDIS=$(echo "$HEALTH"   | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('redis',{}); print('✅' if r.get('available') else '⚠️ ')")
            echo -e "  Status: ${GRN}$STATUS${NC}  Model fitted: ${GRN}${FITTED}${NC}  ML steps: ${CYN}${STEPS}${NC}  Buffer: ${DIM}${BUFFER}${NC}  Redis: $REDIS"
        fi

        # ── OS metrics from API ────────────────────────────
        echo -e "\n${WHT}SYSTEM METRICS${NC}"
        METRICS=$(api_get /os/status)
        if [[ "$METRICS" != "{}" ]]; then
            python3 << PYEOF
import json, sys
d = json.loads('''$METRICS'''.replace("'", '"'))
cpu  = d.get('cpu_percent',0)
mem  = d.get('memory',0)
disk = d.get('disk_percent',0)
ens  = d.get('anomaly_score',0)
h    = d.get('health_score',100)
def col(v, hi=80, med=60):
    if v > hi: return '\033[0;31m'
    if v > med: return '\033[0;33m'
    return '\033[0;32m'
NC='\033[0m'
print(f"  CPU   {col(cpu)}{cpu:5.1f}%{NC}  MEM  {col(mem)}{mem:5.1f}%{NC}  Disk {col(disk)}{disk:5.1f}%{NC}  Anomaly {col(ens*100,50,30)}{ens:.4f}{NC}  Health {col(100-h)}{h:.1f}%{NC}")
PYEOF
        else
            echo -e "  ${DIM}(api unavailable)${NC}"
        fi

        # ── Alert summary ──────────────────────────────────
        echo -e "\n${WHT}ALERTS${NC}"
        ASTATS=$(api_get /alerts/stats)
        python3 -c "
import json, sys
d = json.loads('''$ASTATS'''.replace(\"'\", '\"'))
crit = d.get('critical',0)
warn = d.get('warning',0)
info = d.get('info',0)
cc = '\033[0;31m' if crit > 0 else '\033[2m'
wc = '\033[0;33m' if warn > 0 else '\033[2m'
NC = '\033[0m'
print(f'  {cc}CRITICAL: {crit}{NC}  {wc}WARNING: {warn}{NC}  INFO: {info}  Rules active: {d.get(\"rules_active\",\"?\")}')
" 2>/dev/null || echo -e "  ${DIM}(unavailable)${NC}"

        # ── Recent events from docker logs ────────────────
        echo -e "\n${WHT}RECENT LOG EVENTS${NC}  ${DIM}(last 5 lines from backend)${NC}"
        docker compose logs --no-log-prefix --tail=5 backend 2>/dev/null \
            | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.rstrip()
    try:
        d = json.loads(line)
        lvl = d.get('level','INFO')
        msg = d.get('message','')[:80]
        t   = d.get('time','')[-8:]
        col = '\033[0;31m' if lvl=='ERROR' else '\033[0;33m' if lvl=='WARNING' else '\033[2m'
        NC  = '\033[0m'
        print(f'  {col}{t}  {lvl:<8}{NC}  {msg}')
    except:
        print(f'  \033[2m{line[:90]}\033[0m')
" 2>/dev/null || echo "  (no logs)"

        echo ""
        echo -e "  ${DIM}Refreshing in 3s… Ctrl+C to exit${NC}"
        sleep 3
    done
}

# ─────────────────────────────────────────────────────────
# LOGS — follow all services with colour coding
# ─────────────────────────────────────────────────────────
cmd_logs() {
    echo -e "${CYN}Following logs for all services (Ctrl+C to stop)${NC}"
    docker compose logs -f --tail=50 \
        | python3 -c "
import sys, re
COLORS = {'cvis-backend': '\033[0;36m', 'cvis-nginx': '\033[0;32m',
          'cvis-redis': '\033[0;33m', 'cvis-certbot': '\033[0;35m'}
for line in sys.stdin:
    line = line.rstrip()
    col = '\033[0m'
    for svc, c in COLORS.items():
        if svc in line: col = c; break
    print(f'{col}{line}\033[0m')
" 2>/dev/null
}

# ─────────────────────────────────────────────────────────
# STATS — loop docker stats
# ─────────────────────────────────────────────────────────
cmd_stats() {
    echo -e "${CYN}Docker resource usage (Ctrl+C to stop)${NC}"
    watch -n 2 "docker stats --no-stream --format \
        'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}'"
}

# ─────────────────────────────────────────────────────────
# HEALTH — one-shot JSON health dump
# ─────────────────────────────────────────────────────────
cmd_health() {
    echo -e "${CYN}Health check:${NC} ${API}/health"
    api_get /health | python3 -m json.tool 2>/dev/null || echo "Backend unreachable"
    echo ""
    echo -e "${CYN}ML status:${NC}"
    api_get /ml/status | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  Backend  : {d.get(\"backend\",\"?\")}')
print(f'  Fitted   : {d.get(\"model_fitted\",\"?\")}')
print(f'  LSTM steps: {d.get(\"steps_lstm\",0)}  loss={d.get(\"lstm_loss\",\"?\"):.5f}')
print(f'  VAE steps : {d.get(\"steps_vae\",0)}   recon={d.get(\"vae_recon_loss\",\"?\"):.5f}  kl={d.get(\"vae_kl_loss\",\"?\"):.5f}')
print(f'  Ensemble  : {d.get(\"ensemble_score\",0):.4f}  trend: {d.get(\"lstm_trend\",\"?\")}')
" 2>/dev/null || echo "  ML status unavailable"
}

# ─────────────────────────────────────────────────────────
# ALERTS — recent fired alerts
# ─────────────────────────────────────────────────────────
cmd_alerts() {
    echo -e "${CYN}Recent alerts (last 20):${NC}"
    api_get "/alerts/history?limit=20" | python3 -c "
import sys, json
alerts = json.load(sys.stdin)
if not alerts:
    print('  No alerts fired yet')
    sys.exit()
for a in alerts:
    sev = a.get('severity','?')
    col = '\033[0;31m' if sev=='CRITICAL' else '\033[0;33m' if sev=='WARNING' else '\033[0;36m'
    NC  = '\033[0m'
    import time
    ago = int(time.time() - a.get('fired_at', time.time()))
    print(f'  {col}{sev:<10}{NC}  {ago//60}m ago  {a.get(\"message\",\"\")[:60]}')
" 2>/dev/null
    echo ""
    echo -e "${CYN}Alert stats:${NC}"
    api_get /alerts/stats | python3 -m json.tool 2>/dev/null
}

# ─────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────
case "${1:-dashboard}" in
    dashboard) cmd_dashboard ;;
    logs)      cmd_logs ;;
    stats)     cmd_stats ;;
    health)    cmd_health ;;
    alerts)    cmd_alerts ;;
    *)
        echo "  Usage: bash scripts/monitor.sh [dashboard|logs|stats|health|alerts]"
        exit 1 ;;
esac
