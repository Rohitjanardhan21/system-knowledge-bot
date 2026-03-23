# backend/service_routes.py

from fastapi import APIRouter
import platform
import subprocess

router = APIRouter(prefix="/service")


@router.get("/status")
def service_status():

    return {
        "os": platform.system(),
        "collector_running": True,
        "autostart": False,
        "tray_enabled": True,
    }


@router.post("/collector/restart")
def restart_collector():

    # stub – wire to systemd / Windows Service later
    return {"status": "restart_issued"}


@router.post("/autostart/{enable}")
def autostart(enable: bool):

    return {"autostart": enable}
