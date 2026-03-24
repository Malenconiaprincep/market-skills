"""
盘中极端行情启发式预警（非投资建议）。
规则可通过环境变量微调阈值。
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_intraday_alerts(
    prev: Optional[Dict[str, Any]],
    curr: Dict[str, Any],
    trading_date: str,
) -> List[Dict[str, Any]]:
    """
    prev / curr 为 GLOBAL_STATE['realtime'] 形态：
    { temp, zt, dt, top_stock, top_height, ... }
    """
    out: List[Dict[str, Any]] = []
    zt = int(curr.get("zt") or 0)
    dt = int(curr.get("dt") or 0)
    total = zt + dt
    th = int(curr.get("top_height") or 0)
    stock = str(curr.get("top_stock") or "")

    # 竞价核按钮：跌停占比极高且绝对数量大
    dt_ratio_thr = float(os.environ.get("ALERT_DT_RATIO", "0.45"))
    dt_abs_thr = int(os.environ.get("ALERT_DT_ABS", "25"))
    if total > 0 and (dt / total) >= dt_ratio_thr and dt >= dt_abs_thr:
        out.append(
            {
                "id": str(uuid.uuid4()),
                "level": "critical",
                "title": "竞价核按钮 · 亏钱效应扩散",
                "body": f"{trading_date} 跌停 {dt} / 涨停 {zt}，跌停占比过高，注意风控。",
                "ts": _now_iso(),
            }
        )

    # 龙头高度骤降（相对上一 tick）
    if prev is not None:
        pth = int(prev.get("top_height") or 0)
        if pth >= 5 and th <= max(1, pth - 3):
            out.append(
                {
                    "id": str(uuid.uuid4()),
                    "level": "warning",
                    "title": "龙头高度骤降",
                    "body": f"空间龙连板由 {pth} 降至 {th}（{stock}），高位分歧加剧。",
                    "ts": _now_iso(),
                }
            )

    # 冰点试错：温度极低但略有涨停
    temp = float(curr.get("temp") or 0)
    if temp < 15 and zt >= 3:
        out.append(
            {
                "id": str(uuid.uuid4()),
                "level": "info",
                "title": "冰点试错信号",
                "body": f"情绪温度约 {temp:.1f}°C，仍有 {zt} 家涨停，留意次日修复预期（非建议）。",
                "ts": _now_iso(),
            }
        )

    return out
