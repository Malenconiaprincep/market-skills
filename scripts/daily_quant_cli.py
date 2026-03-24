#!/usr/bin/env python3
"""命令行触发「盘后流水线」（与 main 中 POST /api/admin/post_market_now 等价）。用法：
   cd market-skills && python scripts/daily_quant_cli.py
   python scripts/daily_quant_cli.py 20260324
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.post_market import run_post_market_pipeline  # noqa: E402
from shanghai_calendar import trading_date_str  # noqa: E402

if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else trading_date_str()
    print(json.dumps(run_post_market_pipeline(d), ensure_ascii=False, indent=2))
