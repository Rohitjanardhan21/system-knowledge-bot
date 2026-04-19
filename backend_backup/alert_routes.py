from fastapi import APIRouter, HTTPException
from backend.alerts.store import (
    list_alerts,
    ack_alert,
)

router = APIRouter(prefix="/alerts")


@router.get("/active")
def active_alerts():
    return list_alerts(active_only=True)


@router.get("/history")
def history():
    return list_alerts(active_only=False)

from fastapi import APIRouter, HTTPException
from backend.alerts.store import (
    list_alerts,
    ack_alert,
)

router = APIRouter(prefix="/alerts")


@router.get("/active")
def active_alerts():
    return list_alerts(active_only=True)


@router.get("/history")
def history():
    return list_alerts(active_only=False)


@router.post("/ack/{alert_id}")
def acknowledge(alert_id: str):

    alert = ack_alert(alert_id)

    if not alert:
        raise HTTPException(404, "Alert not found")

    return {"status": "acknowledged", "id": alert_id}
