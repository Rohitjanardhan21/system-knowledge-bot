#!/usr/bin/env bash
# CVIS v9 — Backup & Restore
# Usage:
#   bash scripts/backup.sh backup
#   bash scripts/backup.sh restore 20240115T143022
#   bash scripts/backup.sh list
#   bash scripts/backup.sh verify 20240115T143022
#   bash scripts/backup.sh cron-install
#
# Optional S3: BACKUP_S3_BUCKET=s3://mybucket/cvis bash scripts/backup.sh backup
set -euo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; NC='\033[0m'
info() { echo -e "${BLU}[$(date +%H:%M:%S)]${NC}  $*"; }
ok()   { echo -e "${GRN}  ✓${NC}  $*"; }
warn() { echo -e "${YLW}  ⚠${NC}  $*"; }
die()  { echo -e "${RED}  ✗  FATAL:${NC} $*"; exit 1; }

BACKUP_DIR="${BACKUP_DIR:-./backups}"
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-30}"
TS=$(date -u +%Y%m%dT%H%M%S)
mkdir -p "$BACKUP_DIR"

cmd_backup() {
    SNAP_DIR="$BACKUP_DIR/$TS"; mkdir -p "$SNAP_DIR"
    info "Creating snapshot: $TS"

    # 1. Model versions (JSON registry + weight files)
    if ls model_versions/*.json &>/dev/null 2>&1; then
        tar czf "$SNAP_DIR/model_versions.tar.gz" model_versions/
        ok "Model versions: $(ls model_versions/*.json | wc -l) files"
    else
        warn "No model versions yet"; touch "$SNAP_DIR/model_versions.EMPTY"
    fi

    # 2. Redis BGSAVE + copy dump
    REDIS_OK=false
    if docker compose exec -T redis redis-cli ping &>/dev/null 2>&1; then
        docker compose exec -T redis redis-cli BGSAVE >/dev/null; sleep 2
        REDIS_C=$(docker compose ps -q redis 2>/dev/null | head -1)
        if [[ -n "$REDIS_C" ]]; then
            docker cp "${REDIS_C}:/data/dump.rdb" "$SNAP_DIR/redis.rdb" 2>/dev/null && REDIS_OK=true
            docker cp "${REDIS_C}:/data/cvis.aof" "$SNAP_DIR/redis.aof" 2>/dev/null || true
        fi
        $REDIS_OK && ok "Redis dump.rdb saved" || warn "Redis copy failed"
    else warn "Redis not running — skipping"; fi

    # 3. Ask backend to flush a model version save
    API="${CVIS_API_URL:-http://localhost:8000}"
    API_KEY="${CVIS_API_KEY:-$(grep '^CVIS_API_KEY=' .env 2>/dev/null | cut -d= -f2-)}"
    SAVE_RESP=$(curl -sf -X POST -H "X-API-Key: $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"model_name\":\"ensemble\",\"description\":\"backup $TS\",\"tag\":\"backup\"}" \
        "$API/models/save" 2>/dev/null || echo "{}")
    echo "$SAVE_RESP" | grep -q '"saved":true' \
        && { ok "Live model saved"; echo "$SAVE_RESP" > "$SNAP_DIR/saved_version.json"; } \
        || warn "Backend offline — using on-disk files only"

    # 4. Config digest (no secrets)
    if [[ -f .env ]]; then
        sha256sum .env | awk '{print $1}' > "$SNAP_DIR/env.sha256"
        grep -vE '(PASSWORD|SECRET|KEY|PASS)' .env > "$SNAP_DIR/env.public" || true
        ok ".env digest saved (secrets excluded)"
    fi

    # 5. Manifest
    cat > "$SNAP_DIR/manifest.json" << MEOF
{"timestamp":"$TS","hostname":"$(hostname)","redis_backed":$REDIS_OK,"created_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
MEOF
    docker compose images --format json > "$SNAP_DIR/images.json" 2>/dev/null || true

    # 6. Compress
    ARCHIVE="$BACKUP_DIR/cvis-backup-${TS}.tar.gz"
    tar czf "$ARCHIVE" -C "$BACKUP_DIR" "$TS/"; rm -rf "$SNAP_DIR"
    ok "Archive: $ARCHIVE ($(du -sh "$ARCHIVE" | cut -f1))"

    # 7. Optional S3 upload
    if [[ -n "$S3_BUCKET" ]]; then
        aws s3 cp "$ARCHIVE" "$S3_BUCKET/$(basename "$ARCHIVE")" \
            && ok "Uploaded: $S3_BUCKET" || warn "S3 upload failed"
    fi

    # 8. Prune old backups
    OLD=$(find "$BACKUP_DIR" -name "cvis-backup-*.tar.gz" -mtime "+$RETAIN_DAYS" 2>/dev/null | wc -l)
    [[ $OLD -gt 0 ]] && {
        find "$BACKUP_DIR" -name "cvis-backup-*.tar.gz" -mtime "+$RETAIN_DAYS" -delete
        ok "Pruned $OLD backup(s) older than ${RETAIN_DAYS}d"
    }
    ok "Backup complete"
}

cmd_restore() {
    TS_ARG="${2:-}"; [[ -z "$TS_ARG" ]] && die "Usage: $0 restore <TIMESTAMP>"
    ARCHIVE=$(find "$BACKUP_DIR" -name "cvis-backup-${TS_ARG}.tar.gz" | head -1)
    [[ -z "$ARCHIVE" ]] && die "Not found: $TS_ARG"
    warn "This OVERWRITES model_versions/ and restarts backend."
    read -rp "  Continue? [y/N] " ans; [[ "${ans,,}" != "y" ]] && exit 0

    TMP=$(mktemp -d); trap "rm -rf $TMP" EXIT
    tar xzf "$ARCHIVE" -C "$TMP"
    SNAP=$(ls -d "$TMP"/*/ | head -1)

    [[ -f "$SNAP/model_versions.tar.gz" ]] && {
        mv model_versions "model_versions.bak.$(date +%s)" 2>/dev/null || true
        tar xzf "$SNAP/model_versions.tar.gz"; ok "Model versions restored"
    }
    [[ -f "$SNAP/redis.rdb" ]] && {
        docker compose stop redis
        RC=$(docker compose ps -q redis 2>/dev/null | head -1)
        [[ -n "$RC" ]] && docker cp "$SNAP/redis.rdb" "${RC}:/data/dump.rdb"
        docker compose start redis; ok "Redis restored"
    }
    docker compose restart backend; sleep 3

    [[ -f "$SNAP/saved_version.json" ]] && {
        VID=$(python3 -c "import json; print(json.load(open('$SNAP/saved_version.json')).get('version_id',''))" 2>/dev/null)
        [[ -n "$VID" ]] && {
            curl -sf -X POST -H "X-API-Key: ${CVIS_API_KEY:-}" \
                "http://localhost:8000/models/activate/ensemble/$VID" &>/dev/null \
                && ok "Activated: $VID" || warn "Activate manually via dashboard"
        }
    }
    ok "Restore complete: $TS_ARG"
}

cmd_list() {
    echo ""; echo -e "${BLU}Backups in $BACKUP_DIR:${NC}"; echo ""
    printf "  %-22s %-8s  %s\n" "TIMESTAMP" "SIZE" "AGE"
    echo "  ──────────────────────────────────────"
    find "$BACKUP_DIR" -name "cvis-backup-*.tar.gz" -printf '%f\n' 2>/dev/null | sort -r | \
    while read -r f; do
        TS_P=$(echo "$f" | sed 's/cvis-backup-//; s/\.tar\.gz//')
        SZ=$(du -sh "$BACKUP_DIR/$f" 2>/dev/null | cut -f1)
        AGE=$(( ($(date +%s) - $(stat -c %Y "$BACKUP_DIR/$f" 2>/dev/null || echo 0)) / 86400 ))
        printf "  %-22s %-8s  %sd ago\n" "$TS_P" "$SZ" "$AGE"
    done || echo "  (none)"
    echo ""
}

cmd_verify() {
    TS_ARG="${2:-}"; [[ -z "$TS_ARG" ]] && die "Usage: $0 verify <TIMESTAMP>"
    ARCHIVE=$(find "$BACKUP_DIR" -name "cvis-backup-${TS_ARG}.tar.gz" | head -1)
    [[ -z "$ARCHIVE" ]] && die "Not found: $TS_ARG"
    tar tzf "$ARCHIVE" &>/dev/null && ok "Archive integrity OK" || die "Archive corrupt"
    TMP=$(mktemp -d); trap "rm -rf $TMP" EXIT
    tar xzf "$ARCHIVE" -C "$TMP"
    SNAP=$(ls -d "$TMP"/*/ | head -1)
    [[ -f "$SNAP/manifest.json" ]]          && { ok "Manifest OK"; cat "$SNAP/manifest.json" | python3 -m json.tool | sed 's/^/    /'; }
    [[ -f "$SNAP/model_versions.tar.gz" ]]  && ok "model_versions.tar.gz present" || warn "No model versions"
    [[ -f "$SNAP/redis.rdb" ]]              && ok "redis.rdb present"             || warn "No Redis dump"
    ok "Verification complete"
}

cmd_cron() {
    SCRIPT_PATH="$(realpath "$0")"
    LINE="0 2 * * * cd $(realpath .) && bash $SCRIPT_PATH backup >> logs/backup.log 2>&1"
    (crontab -l 2>/dev/null | grep -v 'cvis.*backup'; echo "$LINE") | crontab -
    ok "Daily backup cron installed at 02:00 UTC"
}

case "${1:-}" in
    backup)        cmd_backup ;;
    restore)       cmd_restore "$@" ;;
    list)          cmd_list ;;
    verify)        cmd_verify "$@" ;;
    cron-install)  cmd_cron ;;
    *)
        echo "  Usage: bash scripts/backup.sh backup | list | restore <TS> | verify <TS> | cron-install"
        echo "  Env:   BACKUP_S3_BUCKET=s3://bucket  BACKUP_RETAIN_DAYS=30"
        exit 1 ;;
esac
