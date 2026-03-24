"""
Vercel Serverless 入口：将 ASGI 应用交给 Mangum。
部署后请用 /health、/api/realtime 等路径；根路径 / 由 main.root 提供。

注意：Vercel 上无法跑 60s 守护线程，盘中实时需 Docker / Railway 等长驻进程。
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from mangum import Mangum  # noqa: E402

from main import app  # noqa: E402

# lifespan="off"：避免在无状态环境里对 startup 重复假设
handler = Mangum(app, lifespan="off")
