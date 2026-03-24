"""冰点试错类强预警：情绪温度大幅回升 + 跌停锐减 → Discord / 飞书。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from market_sentiment_core import MarketSnapshot


@dataclass
class IcePointAlert:
    fired: bool
    reason: str
    prev: Optional[MarketSnapshot]
    curr: MarketSnapshot
    details: dict[str, Any]


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def evaluate_ice_point_reversal(
    morning: MarketSnapshot,
    afternoon: MarketSnapshot,
) -> IcePointAlert:
    """
    默认规则（可通过环境变量微调）：
    - 当前温度 >= ALERT_TEMP_FLOOR（默认 55）
    - 相对早盘升温 >= ALERT_TEMP_DELTA_MIN（默认 30）
    - 跌停数：当前 <= 早盘 * ALERT_DT_RATIO_MAX（默认 0.5），且绝对减少 >= ALERT_DT_DROP_MIN（默认 3）
    """
    t0 = morning.sentiment_temperature()
    t1 = afternoon.sentiment_temperature()
    d0, d1 = morning.dt_count, afternoon.dt_count

    floor = _env_float("ALERT_TEMP_FLOOR", 55.0)
    delta_min = _env_float("ALERT_TEMP_DELTA_MIN", 30.0)
    dt_ratio_max = _env_float("ALERT_DT_RATIO_MAX", 0.5)
    dt_drop_min = _env_int("ALERT_DT_DROP_MIN", 3)

    details: dict[str, Any] = {
        "morning_temp_c": round(t0, 2),
        "afternoon_temp_c": round(t1, 2),
        "morning_dt": d0,
        "afternoon_dt": d1,
        "thresholds": {
            "ALERT_TEMP_FLOOR": floor,
            "ALERT_TEMP_DELTA_MIN": delta_min,
            "ALERT_DT_RATIO_MAX": dt_ratio_max,
            "ALERT_DT_DROP_MIN": dt_drop_min,
        },
    }

    temp_ok = t1 >= floor and (t1 - t0) >= delta_min
    dt_ok = False
    if d0 > 0:
        dt_ok = d1 <= int(d0 * dt_ratio_max) and (d0 - d1) >= dt_drop_min
    elif d0 == 0 and d1 == 0:
        dt_ok = False
    else:
        # 早盘无跌停、尾盘出现跌停，不符合「锐减」叙事
        dt_ok = d1 < d0

    fired = bool(temp_ok and dt_ok)
    reason = ""
    if fired:
        reason = (
            f"情绪温度由早盘约 {t0:.1f}°C 升至约 {t1:.1f}°C，"
            f"跌停由 {d0} 家降至 {d1} 家，疑似冰点试错/抢筹窗口，请结合盘面自主决策。"
        )
    else:
        parts = []
        if not (t1 >= floor and (t1 - t0) >= delta_min):
            parts.append("温度升幅或未达阈值")
        if not dt_ok:
            parts.append("跌停变化未满足「锐减」条件")
        reason = "；".join(parts) if parts else "未触发"

    return IcePointAlert(
        fired=fired,
        reason=reason,
        prev=morning,
        curr=afternoon,
        details=details,
    )


def _post_json(url: str, payload: dict[str, Any], timeout: float = 12.0) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except (urllib.error.URLError, OSError):
        return False


def send_feishu_text(text: str) -> bool:
    hook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not hook:
        return False
    body = {"msg_type": "text", "content": {"text": text}}
    return _post_json(hook, body)


def send_discord_text(text: str) -> bool:
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not hook:
        return False
    return _post_json(hook, {"content": text[:1900]})


def broadcast_strong_alert(title: str, body: str) -> dict[str, bool]:
    """同时尝试飞书与 Discord；返回各渠道是否发送成功。"""
    msg = f"{title}\n\n{body}"
    return {
        "feishu": send_feishu_text(msg),
        "discord": send_discord_text(msg),
    }
