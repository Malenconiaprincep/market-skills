"""盘中数据接口：由前端按需调用 GET /api/intraday?slot=09:40 或 POST JSON {\"slot\":\"14:30\"}。"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from intraday_runner import run_intraday, verify_request_auth  # noqa: E402

from .http_common import handle_options, send_json, unauthorized  # noqa: E402


def _slot_from_query(handler: BaseHTTPRequestHandler) -> str:
    qs = parse_qs(urlparse(handler.path).query)
    slots = qs.get("slot", [])
    return slots[0].strip() if slots else ""


def _slot_from_post(handler: BaseHTTPRequestHandler) -> tuple[str, str | None]:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length).decode("utf-8") if length else ""
    if not raw.strip():
        return "", None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "", "invalid json"
    slot = data.get("slot")
    if slot is None:
        return "", "missing slot in json"
    return str(slot).strip(), None


def dispatch_get(handler: BaseHTTPRequestHandler) -> None:
    if not verify_request_auth(handler.headers):
        unauthorized(handler)
        return
    slot = _slot_from_query(handler)
    if not slot:
        send_json(
            handler,
            {
                "ok": False,
                "error": "missing slot",
                "hint": "GET /api/intraday?slot=09:40 （或 10:30 / 14:30）",
            },
            400,
        )
        return
    _run_and_respond(handler, slot)


def dispatch_post(handler: BaseHTTPRequestHandler) -> None:
    if not verify_request_auth(handler.headers):
        unauthorized(handler)
        return
    slot, err = _slot_from_post(handler)
    if err == "invalid json":
        send_json(handler, {"ok": False, "error": "invalid json"}, 400)
        return
    if err or not slot:
        send_json(
            handler,
            {
                "ok": False,
                "error": err or "missing slot",
                "hint": 'POST {"slot":"14:30"}',
            },
            400,
        )
        return
    _run_and_respond(handler, slot)


def _run_and_respond(handler: BaseHTTPRequestHandler, slot: str) -> None:
    try:
        out = run_intraday(slot)
        if out.get("ok"):
            code = 200
        else:
            err = out.get("error") or ""
            code = 400 if "invalid slot" in err else 500
        send_json(handler, out, code)
    except Exception as e:
        send_json(handler, {"ok": False, "error": str(e)}, 500)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_OPTIONS(self):
        handle_options(self)

    def do_GET(self):
        dispatch_get(self)

    def do_POST(self):
        dispatch_post(self)
