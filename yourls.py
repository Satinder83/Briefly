import os
import requests

YOURLS_API_URL = os.getenv("YOURLS_API_URL", "")
YOURLS_SIGNATURE = os.getenv("YOURLS_SIGNATURE", "")
YOURLS_USERNAME = os.getenv("YOURLS_USERNAME", "")
YOURLS_PASSWORD = os.getenv("YOURLS_PASSWORD", "")


def is_configured() -> bool:
    return bool(YOURLS_API_URL and (YOURLS_SIGNATURE or (YOURLS_USERNAME and YOURLS_PASSWORD)))


def shorten(url: str) -> str | None:
    if not is_configured():
        return None
    payload = {"action": "shorturl", "url": url, "format": "json"}
    if YOURLS_SIGNATURE:
        payload["signature"] = YOURLS_SIGNATURE
    else:
        payload["username"] = YOURLS_USERNAME
        payload["password"] = YOURLS_PASSWORD
    try:
        resp = requests.post(YOURLS_API_URL, data=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("shorturl") or data.get("url", {}).get("shorturl")
    except Exception as e:
        print(f"    [yourls] error: {e}")
        return None
