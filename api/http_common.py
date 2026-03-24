"""Vercel Python 接口共用：CORS、JSON 响应。"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shanghai_calendar import trading_date_str  # noqa: E402


def trade_date_from_query(handler: BaseHTTPRequestHandler) -> tuple[str | None, str | None]:
    """?date=YYYYMMDD 可选；缺省为上海时区当日。显式非法则 (None, err)。"""
    qs = parse_qs(urlparse(handler.path).query)
    dates = qs.get("date", [])
    if not dates:
        return trading_date_str(), None
    d = dates[0].strip()
    if len(d) == 8 and d.isdigit():
        return d, None
    return None, "invalid date, use YYYYMMDD"


def cors_headers(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    origin = handler.headers.get("Origin")
    allow = origin if origin else "*"
    return {
        "Access-Control-Allow-Origin": allow,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
    }


def send_json(handler: BaseHTTPRequestHandler, obj: dict, status: int = 200) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    for k, v in cors_headers(handler).items():
        handler.send_header(k, v)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(body)


def unauthorized(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(401)
    for k, v in cors_headers(handler).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(b"Unauthorized")


def handle_options(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(204)
    for k, v in cors_headers(handler).items():
        handler.send_header(k, v)
    handler.end_headers()


def not_found(handler: BaseHTTPRequestHandler) -> None:
    send_json(handler, {"ok": False, "error": "not found"}, 404)
