"""盘中任务入口：抓取快照、写入状态、在 14:30 对比早盘并触发强预警。"""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from intraday_alerts import (
    IcePointAlert,
    broadcast_strong_alert,
    evaluate_ice_point_reversal,
)
from intraday_state import load_snapshot, save_snapshot, state_backend_configured
from market_sentiment_core import MarketSnapshot, build_snapshot
from shanghai_calendar import trading_date_str

SLOTS = ("09:40", "10:30", "14:30")


def _api_secret() -> str:
    return (
        os.environ.get("INTRADAY_API_SECRET", "").strip()
        or os.environ.get("CRON_SECRET", "").strip()
    )


def verify_request_auth(headers) -> bool:
    """Authorization: Bearer <secret>。优先 INTRADAY_API_SECRET，其次 CRON_SECRET；未配置则不校验（仅本地调试）。"""
    secret = _api_secret()
    if not secret:
        return True
    auth = headers.get("Authorization")
    if not auth:
        return False
    return auth.strip() == f"Bearer {secret}"


def is_sh_weekday() -> bool:
    return datetime.now(ZoneInfo("Asia/Shanghai")).weekday() < 5


def pick_morning_baseline(date: str) -> Optional[MarketSnapshot]:
    """优先 09:40，其次 10:30。"""
    for slot in ("09:40", "10:30"):
        snap = load_snapshot(date, slot)
        if snap is not None:
            return snap
    return None


def run_intraday(slot: str) -> dict[str, Any]:
    """
    执行单次盘中任务。
    - 非工作日：跳过抓取，返回说明（仍 200，避免 Cron 重试风暴）。
    - 快照持久化依赖 UPSTASH_*；未配置时仍可返回当次盘面，但无法跨轮对比。
    """
    slot = slot.strip()
    if slot not in SLOTS:
        return {"ok": False, "error": f"invalid slot, expected one of {SLOTS}"}

    if not is_sh_weekday():
        return {
            "ok": True,
            "skipped": True,
            "reason": "weekend",
            "slot": slot,
        }

    date = trading_date_str()
    err: Optional[str] = None
    snap: Optional[MarketSnapshot] = None
    try:
        snap = build_snapshot(date, slot)
    except Exception:
        err = traceback.format_exc()

    if snap is None:
        return {
            "ok": False,
            "error": err or "build_snapshot failed",
            "slot": slot,
            "date": date,
        }

    saved = save_snapshot(snap)
    result: dict[str, Any] = {
        "ok": True,
        "date": date,
        "slot": slot,
        "snapshot": snap.to_json_dict(),
        "state_saved": saved,
        "state_backend_configured": state_backend_configured(),
    }

    alert: Optional[IcePointAlert] = None
    if slot == "14:30":
        morning = pick_morning_baseline(date)
        if morning is None:
            result["alert"] = {
                "evaluated": False,
                "reason": "no_morning_baseline",
                "hint": "需配置 UPSTASH_REDIS_REST_URL / TOKEN，且 9:40、10:30 已成功写入",
            }
        else:
            alert = evaluate_ice_point_reversal(morning, snap)
            result["alert"] = {
                "evaluated": True,
                "fired": alert.fired,
                "reason": alert.reason,
                "morning_slot": morning.slot,
                "details": alert.details,
            }
            if alert.fired:
                title = "🔥 盘中强预警 · 冰点试错信号（14:30）"
                body = (
                    f"日期 {date} | 对比早盘槽位 {morning.slot}\n"
                    f"涨停 {snap.zt_count} | 跌停 {snap.dt_count} | "
                    f"温度约 {snap.sentiment_temperature():.1f}°C\n"
                    f"{alert.reason}"
                )
                result["notifications"] = broadcast_strong_alert(title, body)

    return result


if __name__ == "__main__":
    import json
    import sys

    _slot = sys.argv[1] if len(sys.argv) > 1 else "14:30"
    print(json.dumps(run_intraday(_slot), ensure_ascii=False, indent=2))
