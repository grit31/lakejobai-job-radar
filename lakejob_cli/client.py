"""HTTP client for lakejob FastAPI backend."""

import os
import httpx

BASE_URL = os.environ.get("LAKEJOB_API", "http://127.0.0.1:8010")


def _post(path: str, json=None, timeout=120):
    try:
        resp = httpx.post(f"{BASE_URL}{path}", json=json, timeout=timeout)
    except httpx.ConnectError:
        resp = httpx.Response(503, text="Cannot connect to lakejob server. Run `lakejob server --start` first.")
    return resp


def _get(path: str, timeout=30):
    try:
        resp = httpx.get(f"{BASE_URL}{path}", timeout=timeout)
    except httpx.ConnectError:
        resp = httpx.Response(503, text="Cannot connect to lakejob server. Run `lakejob server --start` first.")
    return resp


def search(keyword: str, city: str, limit: int = 60):
    return _post("/api/jobs/search", {"keyword": keyword, "city": city, "limit": limit})


def status():
    return _get("/api/status")


def stats():
    return _get("/api/stats")


def jobs(status_filter=None, limit=50):
    q = f"?limit={limit}"
    if status_filter:
        q += f"&status={status_filter}"
    return _get(f"/api/jobs{q}")


def apply_one(job_url: str):
    return _post("/api/jobs/apply", {"job_url": job_url})


def apply_batch(job_urls: list):
    return _post("/api/jobs/apply-batch", {"job_urls": job_urls})


def conversations():
    return _get("/api/conversations")


def chat_messages(conv_id: int):
    return _get(f"/api/conversations/{conv_id}/messages")


def send_message(conv_id: int, content: str):
    return _post(f"/api/conversations/{conv_id}/send", {"content": content})


def doctor():
    return _get("/api/doctor")


def relogin():
    return _post("/api/system/relogin")
