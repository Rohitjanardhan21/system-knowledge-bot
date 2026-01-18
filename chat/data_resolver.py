import requests

API = "http://localhost:8000"

def fetch(path):
    try:
        r = requests.get(API + path, timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def get_cpu(): return fetch("/facts/cpu")
def get_memory(): return fetch("/facts/memory")
def get_storage(): return fetch("/facts/storage")
def get_status(): return fetch("/facts/status")
def get_full_facts(): return fetch("/facts/full")
def get_history(): return fetch("/facts/history")

