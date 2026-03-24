"""盘中快照跨次调用存储（Vercel 无状态函数之间对比用）。可选 Upstash Redis REST。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from market_sentiment_core import MarketSnapshot, snapshot_from_dict


def _state_key(date: str, slot: str) -> str:
    return f"intraday:{date}:{slot}"


def _upstash_config() -> tuple[str, str]:
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    return url, token


def state_backend_configured() -> bool:
    u, t = _upstash_config()
    return bool(u and t)


def save_snapshot(snapshot: MarketSnapshot) -> bool:
    """将快照序列化写入 Upstash；未配置则返回 False。"""
    url, token = _upstash_config()
    if not url or not token:
        return False
    key = _state_key(snapshot.date, snapshot.slot)
    payload = json.dumps(snapshot.to_json_dict(), ensure_ascii=False)
    # Upstash REST：POST /  body: ["SET", key, value]，避免 GET URL 过长
    req_body = json.dumps(["SET", key, payload], ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{url}/", data=req_body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except (urllib.error.URLError, OSError):
        return False


def load_snapshot(date: str, slot: str) -> Optional[MarketSnapshot]:
    url, token = _upstash_config()
    if not url or not token:
        return None
    key = _state_key(date, slot)
    req_url = f"{url}/get/{urllib.parse.quote(key, safe='')}"
    req = urllib.request.Request(req_url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        raw = body.get("result")
        if raw is None or raw == "":
            return None
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        if not isinstance(data, dict):
            return None
        return snapshot_from_dict(data)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TypeError):
        return None
