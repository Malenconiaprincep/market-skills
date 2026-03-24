"""A 股涨跌停与情绪温度（涨停/(涨停+跌停)*100，与 market_sentiment 中 °C 口径一致）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Optional, Tuple

import akshare as ak
import pandas as pd


@dataclass
class MarketSnapshot:
    date: str  # YYYYMMDD
    slot: str  # 如 "09:40"
    zt_count: int
    dt_count: int
    top_height: int
    top_stock: str

    def sentiment_temperature(self) -> float:
        zt, dt = self.zt_count, self.dt_count
        if zt + dt <= 0:
            return 0.0
        return (zt / (zt + dt)) * 100.0

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["temperature_c"] = round(self.sentiment_temperature(), 2)
        return d


def get_market_data(target_date: str) -> Tuple[int, int, int, str]:
    """抓取 A 股情绪核心数据。返回 (涨停数, 跌停数, 最高连板, 空间龙名称)。"""
    df_zt = ak.stock_zt_pool_em(date=target_date)
    zt_count = len(df_zt) if not df_zt.empty else 0

    df_dt = ak.stock_zt_pool_dtgc_em(date=target_date)
    dt_count = len(df_dt) if not df_dt.empty else 0

    top_height = 0
    top_stock = "无"
    if zt_count > 0:
        df_zt_sorted = df_zt.sort_values(by="连板数", ascending=False)
        top_height = int(df_zt_sorted.iloc[0]["连板数"])
        top_stock = str(df_zt_sorted.iloc[0]["名称"])

    return zt_count, dt_count, top_height, top_stock


def df_to_json_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """东方财富涨跌停池 DataFrame → JSON 可序列化行列表。"""
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def get_limit_up_pool(date: str) -> list[dict[str, Any]]:
    """涨停池明细（ak.stock_zt_pool_em）。"""
    df = ak.stock_zt_pool_em(date=date)
    return df_to_json_records(df)


def get_limit_down_pool(date: str) -> list[dict[str, Any]]:
    """跌停池明细（ak.stock_zt_pool_dtgc_em）。"""
    df = ak.stock_zt_pool_dtgc_em(date=date)
    return df_to_json_records(df)


def build_snapshot(date: str, slot: str) -> MarketSnapshot:
    zt, dt, height, stock = get_market_data(date)
    return MarketSnapshot(
        date=date,
        slot=slot,
        zt_count=zt,
        dt_count=dt,
        top_height=height,
        top_stock=stock,
    )


def snapshot_from_dict(d: dict[str, Any]) -> Optional[MarketSnapshot]:
    try:
        return MarketSnapshot(
            date=str(d["date"]),
            slot=str(d["slot"]),
            zt_count=int(d["zt_count"]),
            dt_count=int(d["dt_count"]),
            top_height=int(d["top_height"]),
            top_stock=str(d["top_stock"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
