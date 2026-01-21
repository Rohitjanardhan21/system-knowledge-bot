# System Knowledge Bot

An internal, offline assistant that answers questions about a Linux system by
combining real system telemetry with deterministic reasoning and natural language explanations.

This is **not a public chatbot**. It is designed as an **internal system intelligence tool**.

---

## Why This Exists

System tools usually either expose raw metrics or give generic advice.
This project bridges that gap by grounding explanations in **real system data**
and clearly stating uncertainty when information is unavailable.

---

## Architecture (High Level)

Linux System
↓
System Collector
↓
System Facts (JSON)
↓
Backend API (FastAPI)
↓
Reasoning Engine
↓
Chat Interface (CLI)

yaml
Copy code

Each layer has a single responsibility and fails safely.

---

## Key Features

- CPU, memory, and storage introspection  
- System health evaluation  
- Cause–effect reasoning (e.g., “Why is my system slow?”)  
- Hardware degradation awareness (disk / battery)  
- Change detection across runs  
- Explicit uncertainty handling  
- Fully offline operation  

---

## What This System Does NOT Do

- It does not guess or hallucinate  
- It does not auto-fix system issues  
- It does not require internet access  

If data is unavailable, the system explains why.

---

## How to Run (Local)

```bash
python3 system_collector/collect_system.py
uvicorn backend.main:app --port 8000
python3 -m chat.chat_cli
Docker
bash
Copy code
docker build -t system-knowledge-bot:1.0 .
docker run -p 8000:8000 system-knowledge-bot:1.0
Verify:

bash
Copy code
curl http://localhost:8000/health
Reliability & SRE Thinking
SLIs

API availability (/health)

Data freshness (non-stale facts)

Failures are handled explicitly and explained to the user.

Project Status
Phase 1: System telemetry — complete

Phase 2: Reasoning & intelligence — complete

Phase 3: DevOps & SRE — in progress

Future Work
Virtual assistant interface (voice / GUI)

Proactive alerts

Multi-node support
