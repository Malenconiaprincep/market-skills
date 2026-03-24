"""涨停池明细：GET /api/limit_up?date=YYYYMMDD（date 可选）。"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from intraday_runner import verify_request_auth  # noqa: E402
from market_sentiment_core import get_limit_up_pool  # noqa: E402

from .http_common import handle_options, send_json, trade_date_from_query, unauthorized  # noqa: E402


def dispatch_get(handler: BaseHTTPRequestHandler) -> None:
    if not verify_request_auth(handler.headers):
        unauthorized(handler)
        return
    date, err = trade_date_from_query(handler)
    if err:
        send_json(handler, {"ok": False, "error": err}, 400)
        return
    assert date is not None
    try:
        rows = get_limit_up_pool(date)
        send_json(
            handler,
            {
                "ok": True,
                "date": date,
                "pool": "limit_up",
                "count": len(rows),
                "rows": rows,
            },
        )
    except Exception as e:
        send_json(handler, {"ok": False, "error": str(e)}, 500)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_OPTIONS(self):
        handle_options(self)

    def do_GET(self):
        dispatch_get(self)
