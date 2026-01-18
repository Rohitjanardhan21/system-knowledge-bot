FROM python:3.11-slim

WORKDIR /app

COPY backend backend
COPY chat chat
COPY knowledge knowledge
COPY system_facts/history system_facts/history

RUN pip install fastapi uvicorn requests

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
