# CVIS — Cognitive AIOps Engine

> Note: Live demo runs on Render free tier — disk metric shows 100% due to 
> container filesystem limits. Local/Docker installs show real disk usage.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render-green)](https://cvis-os-latest.onrender.com)
[![Docker](https://img.shields.io/badge/Docker-rohitjanardhan%2Fcvis--os-blue)](https://hub.docker.com/r/rohitjanardhan/cvis-os)

> Predicts system failures before they happen. Runs 100% locally.

**[Live Demo](https://cvis-os-latest.onrender.com)** | [Docker Hub](https://hub.docker.com/r/rohitjanardhan/cvis-os)

## Quickstart — 30 seconds
```bash
docker run -p 8000:8000 rohitjanardhan/cvis-os:latest
```
Open http://localhost:8000


## Architecture

```
Browser (CVIS Dashboard)
  │  JWT / API-key auth on every request
  ▼
nginx :443  (TLS, rate-limit, SPA)
  │
  ├─ /os/* /ml/* /models/* /alerts/* ──► Gunicorn + FastAPI :8000
  │                                           │
  │         ┌─────────────────────────────────┤
  │         │  ML Engine (background thread)  │
  │         │  ├ PyTorch LSTM  2-layer, BPTT  │
  │         │  ├ β-VAE  5→16→8→4→8→16→5       │
  │         │  └ sklearn IF  100 estimators   │
  │         │                                 │
  │         │  Model Registry  (versioning)   │
  │         │  Alert Engine    (webhooks+SMTP) │
  │         └─────────────────────────────────┘
  │
  └─ /grafana/ ──► Grafana :3000
                       │
                       └─ Prometheus :9090 ─► /metrics (21 gauges)

Redis :6379
  ├ alert cooldown dedup  (SET NX EX)
  ├ rate-limit counters   (cross-worker)
  ├ metric snapshot cache (TTL 3s)
  ├ JWT blocklist          (JTI revocation)
  └ pub/sub event bus     (worker sync)
```

---

## Quickstart (local dev, no Docker)

```bash
pip install fastapi uvicorn psutil scikit-learn numpy httpx torch PyJWT
python backend_v9.py          # http://localhost:8000
open frontend/index.html      # or: python -m http.server 3000 -d frontend
```

---

## Production deploy (Ubuntu 22.04 EC2)

**One command from scratch:**
```bash
# Set env vars, then run as root:
DOMAIN=yourdomain.com ACME_EMAIL=ops@you.com \
  sudo bash scripts/bootstrap.sh
```

This installs Docker, hardens ufw/fail2ban, generates secrets, builds images, and starts all services.

**Manual steps:**
```bash
# 1. Generate secrets
bash scripts/secrets-setup.sh generate       # creates .env with random keys

# 2. Set your domain
sed -i 's/yourdomain.com/acme.example.com/g' .env

# 3. Build + start
docker compose up -d --build

# 4. HTTPS — choose one:
bash scripts/https-setup.sh cloudflare                           # Cloudflare proxy
bash scripts/https-setup.sh letsencrypt yourdomain.com ops@you  # Let's Encrypt
```

---

## HTTPS

| Method | Setup time | Renewal | Best for |
|---|---|---|---|
| **Cloudflare** | 5 min | Automatic at edge | Most deployments |
| **Let's Encrypt** | 10 min | Auto via certbot container | Self-hosted, no CDN |

Both paths are scripted: `bash scripts/https-setup.sh cloudflare` or `letsencrypt`.

---

## Authentication

Every endpoint requires a credential. Three ways to authenticate:

```bash
# 1. API key header (machine-to-machine, CI/CD)
curl -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/ml/status

# 2. JWT — login, then use Bearer token (browser sessions)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-pass"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/ml/status

# 3. JWT refresh (tokens expire in 15 min; refresh_token lasts 7 days)
NEW=$(curl -s -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH\"}" | jq -r .access_token)
```

**Scope levels:**

| Scope | Endpoints | Who |
|---|---|---|
| `read` | GET /os/*, /ml/*, /models/*, /alerts/* | Dashboard, monitoring |
| `write` | POST /alerts/webhooks, /ml/scores | Services, integrations |
| `admin` | POST/DELETE /models/*, /alerts/rules, /auth/api-keys | Operators |
| *(public)* | GET /health, GET /metrics | Load balancers, Prometheus |

```bash
# Create a read-only key for your monitoring service
curl -X POST -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/auth/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name":"grafana-read","scope":"read"}'
```

---

## ML Models

Three models run in parallel on a 512-entry replay buffer, training in batches of 32 every 5 ticks:

| Model | Architecture | Anomaly signal |
|---|---|---|
| **PyTorch LSTM** | 2-layer, h=64, LayerNorm, Adam, grad-clip=1.0 | Next-timestep prediction error |
| **β-VAE** | 5→16→8→4→8→16→5, BatchNorm, LeakyReLU, β=0.5 | Reconstruction loss + KL divergence |
| **sklearn IF** | 100 estimators, contamination=0.08, RobustScaler | Isolation path length |

Ensemble: `IF×0.40 + VAE×0.35 + LSTM×0.25`

All three warm up within ~60 ticks (~1 minute at default poll rate).

---

## Model versioning

```bash
# Save the current model weights manually
curl -X POST -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/models/save \
  -H "Content-Type: application/json" \
  -d '{"description":"pre-deploy snapshot","tag":"stable"}'

# List all saved versions
curl -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/models/versions

# Roll back to the previous version
curl -X POST -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/models/rollback/ensemble

# Restore the best-scoring version ever recorded
curl -X POST -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/models/rollback_best/ensemble

# Activate a specific version by ID
curl -X POST -H "X-API-Key: $CVIS_API_KEY" \
  http://localhost:8000/models/activate/ensemble/ensemble_1704067200_abc123
```

Models auto-save every 5 minutes when training steps > 50. Up to 10 versions are retained per model family; oldest pruned first, `active` and `is_best` are never pruned.

---

## Alerts

```bash
# Add a Slack webhook
curl -X POST -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/alerts/webhooks \
  -H "Content-Type: application/json" \
  -d '{"url":"https://hooks.slack.com/services/T.../B.../xxx","name":"ops-slack"}'

# Test it
curl -X POST -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/alerts/webhooks/{id}/test

# Configure email (Gmail example)
curl -X PUT -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/alerts/email \
  -H "Content-Type: application/json" \
  -d '{"host":"smtp.gmail.com","port":587,"username":"you@gmail.com",
       "password":"app-password","from_addr":"you@gmail.com",
       "to_addrs":["team@yourco.com"]}'

# Add a custom rule
curl -X POST -H "X-API-Key: $CVIS_API_KEY" http://localhost:8000/alerts/rules \
  -H "Content-Type: application/json" \
  -d '{"name":"Ensemble spike","metric":"ensemble","operator":"gt",
       "threshold":0.75,"severity":"CRITICAL","cooldown_s":120}'

# View recent alerts
curl -H "X-API-Key: $CVIS_API_KEY" "http://localhost:8000/alerts/history?limit=20"
```

Default rules: CPU >90% (CRITICAL), CPU >75% (WARNING), MEM >90%, MEM >75%, Disk >85%, Anomaly >0.8, Health <60%.

---

## Monitoring

```bash
# Live terminal dashboard (refreshes every 3s)
bash scripts/monitor.sh

# Specific views
bash scripts/monitor.sh logs     # colour-coded log follow
bash scripts/monitor.sh stats    # docker stats loop
bash scripts/monitor.sh health   # one-shot JSON health dump
bash scripts/monitor.sh alerts   # recent fired alerts

# Grafana (pre-built 9-panel dashboard)
# Access via SSH tunnel:
ssh -L 3000:localhost:3000 user@yourserver
# Then open: http://localhost:3000  (admin / $GRAFANA_PASS from .env)
```

**Prometheus metrics** (21 gauges, no auth, scraped every 10s at `/metrics`):

```
cvis_cpu_percent           cvis_memory_percent       cvis_health_score
cvis_anomaly_score         cvis_ml_if_score          cvis_ml_vae_score
cvis_ml_lstm_score         cvis_ml_ensemble_score    cvis_ml_lstm_loss
cvis_ml_vae_recon_loss     cvis_ml_vae_kl_loss       cvis_ml_steps_lstm
cvis_ml_steps_vae          cvis_ml_model_fitted      cvis_ml_feature_buffer_size
cvis_alerts_critical_total cvis_alerts_warning_total cvis_alerts_info_total
cvis_alerts_rules_active   cvis_model_versions_total cvis_disk_percent
```

---

## Backup & restore

```bash
# Create a snapshot (model weights + Redis + .env digest)
bash scripts/backup.sh backup

# List snapshots
bash scripts/backup.sh list

# Restore a specific snapshot
bash scripts/backup.sh restore 20240115T143022

# Verify archive integrity
bash scripts/backup.sh verify 20240115T143022

# Install daily 02:00 UTC cron
bash scripts/backup.sh cron-install

# Optional S3 offsite
BACKUP_S3_BUCKET=s3://mybucket/cvis bash scripts/backup.sh backup
```

---

## Secrets management

```bash
# Generate a fresh .env (run once on first deploy)
bash scripts/secrets-setup.sh generate

# Rotate a specific secret (restarts backend automatically)
bash scripts/secrets-setup.sh rotate jwt
bash scripts/secrets-setup.sh rotate apikey
bash scripts/secrets-setup.sh rotate adminpass

# Push secrets to Docker Swarm encrypted store (production)
bash scripts/secrets-setup.sh docker-secrets
```

Secrets are read in priority order: Docker Swarm secret file (`/run/secrets/`) → `_FILE` env var → plain env var. The `.env` file is blocked from git by `.gitignore`.

---

## Load testing

```bash
pip install locust

# Smoke test (30s, 10 users)
CVIS_API_KEY=$CVIS_API_KEY \
  locust -f scripts/load_test.py --host http://localhost:8000 \
  --headless -u 10 -r 2 -t 30s --only-summary

# Ramp test (5 min, 50 concurrent users)
CVIS_API_KEY=$CVIS_API_KEY \
  locust -f scripts/load_test.py --host http://localhost:8000 \
  --headless -u 50 -r 5 -t 5m --only-summary

# Interactive UI
CVIS_API_KEY=$CVIS_API_KEY \
  locust -f scripts/load_test.py --host http://localhost:8000
# Open http://localhost:8089
```

SLO targets: p50 <50ms (health), p95 <200ms (ml/status, ml/scores), error rate <0.1%.

---

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`):

| Job | Trigger | What it does |
|---|---|---|
| `lint` | Every push | `ruff check` + `mypy` |
| `test` | After lint | pytest with real Redis service container |
| `build` | After test | Multi-arch Docker image → GHCR |
| `security` | After build | Trivy CVE scan + pip-audit |
| `deploy-staging` | `develop` branch | SSH deploy + smoke test |
| `deploy-production` | GitHub Release tag | SSH deploy + Slack notification |

Required GitHub secrets: `JWT_SECRET`, `CVIS_API_KEY`, `CVIS_ADMIN_PASS`, `STAGING_HOST`, `STAGING_SSH_KEY`, `PROD_HOST`, `PROD_SSH_KEY`, `SLACK_WEBHOOK_URL`.

---

## Cloud deployment

### AWS ECS (Fargate)
```bash
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_URI
docker build -t cvis-backend . && docker tag cvis-backend:latest $ECR_URI/cvis-backend:latest
docker push $ECR_URI/cvis-backend:latest
# Create ECS task definition, mount EFS for /app/model_versions
```

### GCP Cloud Run
```bash
gcloud builds submit --tag gcr.io/$PROJECT/cvis-backend
gcloud run deploy cvis-backend \
  --image gcr.io/$PROJECT/cvis-backend \
  --memory 2Gi --cpu 2 --platform managed --allow-unauthenticated
```

### Kubernetes
```bash
kubectl apply -f k8s/   # see README for manifest snippets
```

---

## Project structure

```
cvis_v9/
├── backend_v9.py          FastAPI app — all endpoints
├── ml_engine.py           PyTorch LSTM + β-VAE + sklearn IF
├── model_registry.py      Version store with rollback
├── alert_engine.py        Webhooks + SMTP + rules engine
├── auth.py                JWT + API-key auth, Docker secrets
├── redis_store.py         Dedup, rate-limit, cache, pub/sub
├── logging_config.py      JSON logging, Loki, correlation IDs
├── gunicorn_conf.py       Multi-worker production config
├── pyproject.toml         ruff + mypy + pytest + coverage
├── Dockerfile             Multi-stage, non-root, healthcheck
├── docker-compose.yml     Full stack: backend+nginx+redis+prometheus+grafana
├── .dockerignore          Keeps .env and weights out of build context
├── .gitignore             Keeps secrets out of git
├── .env.example           Template — copy to .env and fill in
├── nginx/
│   ├── nginx.conf         TLS, HSTS, OCSP, rate-limit, Grafana proxy
│   ├── Dockerfile         certbot + self-signed fallback
│   └── docker-entrypoint-nginx.sh
├── monitoring/
│   ├── prometheus.yml     Scrape config
│   ├── grafana-datasource.yml
│   ├── grafana-dashboard.yml
│   └── dashboards/cvis-main.json  9-panel pre-built dashboard
├── scripts/
│   ├── bootstrap.sh       Fresh EC2 → running CVIS in one command
│   ├── https-setup.sh     Cloudflare or Let's Encrypt TLS
│   ├── secrets-setup.sh   Generate, rotate, push to Docker secrets
│   ├── backup.sh          Snapshot + restore + S3 offload
│   ├── monitor.sh         Terminal dashboard + logs + alerts
│   ├── load_test.py       Locust load test with SLO validation
│   └── deploy.sh          Rolling deploy helper
├── tests/
│   ├── conftest.py        Shared fixtures, mock Redis, ML helpers
│   ├── test_suite.py      Auth, ML, alert engine, API endpoints
│   └── test_refresh_redis_load.py  Token refresh, Redis, concurrency
└── frontend/
    └── index.html         CVIS dashboard SPA (no build step)
```

---

## API reference

Full interactive docs at `http://localhost:8000/docs` (disabled in `ENV=prod` — use staging).

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Service health + ML status |
| GET | `/metrics` | none | Prometheus metrics (21 gauges) |
| POST | `/auth/login` | none | Get JWT access+refresh tokens |
| POST | `/auth/refresh` | none | Silently rotate expired access token |
| POST | `/auth/api-keys` | admin | Create scoped API key |
| GET | `/os/status` | read | Live CPU/mem/disk/anomaly metrics |
| GET | `/os/processes` | read | Top processes by CPU and memory |
| GET | `/ml/status` | read | All ML model scores + training state |
| POST | `/ml/scores` | read | Score a feature vector |
| GET | `/ml/vae/analysis` | read | VAE latent space + feature errors |
| POST | `/models/save` | admin | Snapshot current model weights |
| GET | `/models/versions` | read | List saved versions |
| POST | `/models/rollback/{name}` | admin | Revert to previous version |
| POST | `/models/rollback_best/{name}` | admin | Restore best-scoring version |
| POST | `/models/activate/{name}/{id}` | admin | Load a specific version |
| GET | `/alerts/history` | read | Recent fired alerts |
| GET | `/alerts/stats` | read | Alert counts by severity |
| GET | `/alerts/rules` | read | Active alert rules |
| POST | `/alerts/rules` | admin | Add alert rule |
| DELETE | `/alerts/rules/{id}` | admin | Delete rule |
| POST | `/alerts/webhooks` | write | Register webhook target |
| PUT | `/alerts/email` | admin | Configure SMTP email |
