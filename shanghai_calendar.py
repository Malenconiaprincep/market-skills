"""上海时区交易日历字符串（YYYYMMDD）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def trading_date_str() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")


def in_trading_window() -> bool:
    """工作日连续竞价时段 09:25–15:00（上海）。与 main 守护线程盘中分支一致。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 25) <= t < (15 * 60)
