"""
盘后 15:05 流水线：拉取收盘数据 → 大模型复盘 → 写入飞书多维表格。
与 daily_quant_bot / 前端飞书列约定对齐，便于「复盘页」继续读同一张表。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from market_sentiment_core import get_market_data

from services.feishu_service import append_sentiment_row, fetch_sentiment_history_for_dashboard
from services.llm_service import cycle_phase_from_temperature, generate_ai_recap

logger = logging.getLogger(__name__)


def sentiment_temperature(zt: int, dt: int) -> float:
    if zt + dt <= 0:
        return 0.0
    return (zt / (zt + dt)) * 100.0


def _norm_date_key(val: Any) -> str:
    s = str(val or "").strip()
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def run_post_market_pipeline(trading_date_yyyymmdd: str) -> Dict[str, Any]:
    """
    trading_date_yyyymmdd: YYYYMMDD（上海交易日）。
    返回结构化结果供日志与 API 调试。
    """
    target_display = f"{trading_date_yyyymmdd[:4]}-{trading_date_yyyymmdd[4:6]}-{trading_date_yyyymmdd[6:8]}"

    # 已存在同日记录则跳过，避免 15:05 窗口内每分钟重复写入
    try:
        records, err = fetch_sentiment_history_for_dashboard(days=40)
        if err is None and records:
            for r in records:
                fd = r.get("fields", {}).get("date")
                if _norm_date_key(fd) == target_display:
                    return {
                        "ok": True,
                        "skipped": True,
                        "reason": "already_in_feishu",
                        "date": trading_date_yyyymmdd,
                    }
    except Exception as e:
        logger.warning("查重失败，继续写入：%s", e)

    zt, dt, height, stock = get_market_data(trading_date_yyyymmdd)
    temp = sentiment_temperature(zt, dt)
    phase, note = cycle_phase_from_temperature(temp)

    ai_text: Optional[str] = None
    err_llm: Optional[str] = None
    try:
        ai_text = generate_ai_recap(trading_date_yyyymmdd, zt, dt, height, stock)
    except Exception as e:
        err_llm = str(e)
        logger.exception("LLM 复盘失败")
        ai_text = f"（AI 生成失败：{err_llm}）"

    date_display = target_display

    ok_fs: Optional[bool] = None
    err_fs: Optional[str] = None
    try:
        ok_fs, err_fs = append_sentiment_row(
            date_display=date_display,
            zt_count=zt,
            dt_count=dt,
            temperature=temp,
            ai_recap_text=ai_text or "",
            top_stock=stock,
            top_height=height,
        )
    except Exception as e:
        ok_fs = False
        err_fs = str(e)
        logger.exception("飞书写入失败")

    return {
        "ok": bool(ok_fs),
        "date": trading_date_yyyymmdd,
        "zt_count": zt,
        "dt_count": dt,
        "temperature": round(temp, 2),
        "top_height": height,
        "top_stock": stock,
        "cycle_phase": phase,
        "cycle_note": note,
        "ai_recap_text": ai_text,
        "feishu_written": ok_fs,
        "feishu_error": err_fs,
        "llm_error": err_llm,
    }


def append_sentiment_openclaw_no_llm(trading_date_yyyymmdd: str) -> Dict[str, Any]:
    """
    供 OpenClaw / market_sentiment.py：仅同步东财盘面数字到飞书情绪表，不调用大模型；
    「情绪结论」写入占位句。查重逻辑与 run_post_market_pipeline 一致。
    """
    target_display = f"{trading_date_yyyymmdd[:4]}-{trading_date_yyyymmdd[4:6]}-{trading_date_yyyymmdd[6:8]}"

    try:
        records, err = fetch_sentiment_history_for_dashboard(days=40)
        if err is None and records:
            for r in records:
                fd = r.get("fields", {}).get("date")
                if _norm_date_key(fd) == target_display:
                    return {
                        "ok": True,
                        "skipped": True,
                        "reason": "already_in_feishu",
                        "date": trading_date_yyyymmdd,
                        "llm_used": False,
                    }
    except Exception as e:
        logger.warning("查重失败，继续写入：%s", e)

    zt, dt, height, stock = get_market_data(trading_date_yyyymmdd)
    temp = sentiment_temperature(zt, dt)
    phase, note = cycle_phase_from_temperature(temp)
    placeholder = "（OpenClaw / market_sentiment.py 同步，未生成 AI 复盘）"

    ok_fs: Optional[bool] = None
    err_fs: Optional[str] = None
    try:
        ok_fs, err_fs = append_sentiment_row(
            date_display=target_display,
            zt_count=zt,
            dt_count=dt,
            temperature=temp,
            ai_recap_text=placeholder,
            top_stock=stock,
            top_height=height,
        )
    except Exception as e:
        ok_fs = False
        err_fs = str(e)
        logger.exception("飞书写入失败")

    return {
        "ok": bool(ok_fs),
        "skipped": False,
        "date": trading_date_yyyymmdd,
        "zt_count": zt,
        "dt_count": dt,
        "temperature": round(temp, 2),
        "top_height": height,
        "top_stock": stock,
        "cycle_phase": phase,
        "cycle_note": note,
        "feishu_written": ok_fs,
        "feishu_error": err_fs,
        "llm_used": False,
    }


def feishu_history_payload() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """供 GET /api/history 使用。"""
    records, err = fetch_sentiment_history_for_dashboard(days=15)
    if err:
        return None, err
    return {"ok": True, "records": records, "source": "feishu"}, None
