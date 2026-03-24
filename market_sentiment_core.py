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


def _top_height_and_stock_from_zt_df(df_zt: pd.DataFrame) -> Tuple[int, str]:
    """从涨停池 DataFrame 取最高连板与名称（空池则 0 /「无」）。"""
    if df_zt is None or df_zt.empty:
        return 0, "无"
    df_sorted = df_zt.sort_values(by="连板数", ascending=False)
    return int(df_sorted.iloc[0]["连板数"]), str(df_sorted.iloc[0]["名称"])


def _limit_pct_for_stock(code: Any, name: Any) -> float:
    """
    按代码/名称估算涨跌停幅度（%），用于 stock_zh_a_spot_em 行判断。
    ST/*ST/退市风险约 5%；创业板/科创板 20%；北交所常见 30%；其余主板约 10%。
    """
    ns = str(name or "")
    if "ST" in ns.upper() or "*ST" in ns.upper() or "退" in ns:
        return 5.0
    c = str(code or "").strip()
    head3 = c[:3] if len(c) >= 3 else c.zfill(6)[:3]
    head1 = c[0] if c else ""
    if head3 in ("300", "301", "688"):
        return 20.0
    if head1 in ("8", "4") or c.startswith("920"):
        return 30.0
    return 10.0


def count_limit_up_down_from_spot_em(df: pd.DataFrame) -> Tuple[int, int]:
    """
    基于东财 A 股实时行情 `stock_zh_a_spot_em` 全表，按「涨跌幅」与个股涨跌停幅度估算涨停/跌停家数。
    """
    if df is None or df.empty or "涨跌幅" not in df.columns:
        return 0, 0
    code_col = "代码" if "代码" in df.columns else None
    name_col = "名称" if "名称" in df.columns else None
    if not code_col or not name_col:
        return 0, 0
    pct = pd.to_numeric(df["涨跌幅"], errors="coerce")
    zt = dt = 0
    tol = 0.11
    for i in range(len(df)):
        p = pct.iloc[i]
        if pd.isna(p):
            continue
        lim = _limit_pct_for_stock(df.iloc[i].get(code_col), df.iloc[i].get(name_col))
        if p >= lim - tol:
            zt += 1
        elif p <= -lim + tol:
            dt += 1
    return zt, dt


def get_market_data(target_date: str) -> Tuple[int, int, int, str]:
    """抓取 A 股情绪核心数据（东财涨/跌停池，适合盘后或与日终池一致场景）。"""
    df_zt = ak.stock_zt_pool_em(date=target_date)
    zt_count = len(df_zt) if not df_zt.empty else 0

    df_dt = ak.stock_zt_pool_dtgc_em(date=target_date)
    dt_count = len(df_dt) if not df_dt.empty else 0

    top_height, top_stock = _top_height_and_stock_from_zt_df(df_zt)

    return zt_count, dt_count, top_height, top_stock


def get_market_data_realtime_spot(target_date: str) -> Tuple[int, int, int, str]:
    """
    盘中实时：涨跌停家数用 `ak.stock_zh_a_spot_em()` 全市场行情统计；
    最高连板与空间龙仍用当日 `stock_zt_pool_em`（含连板数），与网页涨停池展示一致。
    """
    df_spot = ak.stock_zh_a_spot_em()
    zt_count, dt_count = count_limit_up_down_from_spot_em(df_spot)

    df_zt = ak.stock_zt_pool_em(date=target_date)
    top_height, top_stock = _top_height_and_stock_from_zt_df(df_zt)

    return zt_count, dt_count, top_height, top_stock


def df_to_json_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """东方财富涨跌停池 DataFrame → JSON 可序列化行列表。"""
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def get_limit_up_pool(date: str) -> list[dict[str, Any]]:
    """涨停池明细（ak.stock_zt_pool_em）。行内含东财字段如「代码」「名称」「连板数」「所属行业」等，与 market_sentiment 脚本列一致。"""
    df = ak.stock_zt_pool_em(date=date)
    return df_to_json_records(df)


def get_limit_down_pool(date: str) -> list[dict[str, Any]]:
    """跌停池明细（ak.stock_zt_pool_dtgc_em）。"""
    df = ak.stock_zt_pool_dtgc_em(date=date)
    return df_to_json_records(df)


def build_snapshot_intraday_live(date: str, slot: str) -> MarketSnapshot:
    """盘中连续竞价：涨跌停家数用 stock_zh_a_spot_em，失败则回退涨跌停池。"""
    try:
        zt, dt, height, stock = get_market_data_realtime_spot(date)
    except Exception:
        zt, dt, height, stock = get_market_data(date)
    return MarketSnapshot(
        date=date,
        slot=slot,
        zt_count=zt,
        dt_count=dt,
        top_height=height,
        top_stock=stock,
    )


def build_snapshot_daily_pools(date: str, slot: str) -> MarketSnapshot:
    """非盘中或收盘后：东财当日涨跌停池条数（与 /api/limit_up|down 列表口径一致，非瞬时 spot）。"""
    zt, dt, height, stock = get_market_data(date)
    return MarketSnapshot(
        date=date,
        slot=slot,
        zt_count=zt,
        dt_count=dt,
        top_height=height,
        top_stock=stock,
    )


def build_snapshot(date: str, slot: str) -> MarketSnapshot:
    """兼容旧名：等同盘中实时快照。"""
    return build_snapshot_intraday_live(date, slot)


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
