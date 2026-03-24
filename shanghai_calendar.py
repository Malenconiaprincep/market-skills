"""上海时区交易日历字符串（YYYYMMDD）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def trading_date_str() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
