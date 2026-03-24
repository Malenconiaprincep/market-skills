"""本地开发：多路由 HTTP，与 Vercel 的 /api/* 路径一致。"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from api.http_common import handle_options, not_found  # noqa: E402


class RouterHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_OPTIONS(self):
        handle_options(self)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/api/intraday":
            from api.intraday import dispatch_post

            dispatch_post(self)
            return
        not_found(self)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/api/intraday":
            from api.intraday import dispatch_get

            dispatch_get(self)
            return
        if path == "/api/limit_up":
            from api.limit_up import dispatch_get as dg

            dg(self)
            return
        if path == "/api/limit_down":
            from api.limit_down import dispatch_get as dg

            dg(self)
            return
        not_found(self)


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "3000"))
    httpd = HTTPServer((host, port), RouterHandler)
    print(f"http://{host}:{port}/api/intraday?slot=09:40")
    print(f"http://{host}:{port}/api/limit_up")
    print(f"http://{host}:{port}/api/limit_down")
    print("Ctrl+C 停止")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
