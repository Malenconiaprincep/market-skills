#!/usr/bin/env python3
"""
OpenClaw 编排用：与 market_sentiment_core + FastAPI（/api/limit_up、实时快照）同源数据；
stdout 可再接飞书机器人；也可本脚本直接写入飞书情绪表。

数据口径：
  - 涨停/跌停家数、空间龙、连板高度：get_market_data（= main.py 盘中/盘后同一套 akshare）
  - 情绪温度：(涨停 / (涨停+跌停)) * 100，与 market_sentiment_core.MarketSnapshot 一致
  - 列表展示列：与东财涨停池一致，含「所属行业」（get_limit_up_pool）

示例：
  python market_sentiment.py
  python market_sentiment.py --date 20260324
  python market_sentiment.py --json
  python market_sentiment.py --write-feishu              # 仅写盘面数字，情绪结论为占位句
  python market_sentiment.py --write-feishu --with-llm   # 等同盘后流水线（LLM + 飞书）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from market_sentiment_core import get_limit_up_pool, get_market_data
from services.post_market import (
    append_sentiment_openclaw_no_llm,
    run_post_market_pipeline,
    sentiment_temperature,
)


def _today_yyyymmdd_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")


def _print_top_limit_up(df_rows: List[Dict[str, Any]], limit: int = 10) -> None:
    """按连板数降序，打印代码/名称/所属行业等（与网页 limit_up 接口字段同源）。"""
    if not df_rows:
        print("涨停池为空（非交易日或接口异常）。")
        return
    cols_show = ["代码", "名称", "所属行业", "涨跌幅", "最新价", "连板数"]
    # 若某列不存在（接口变更），只打印存在的列
    first = df_rows[0]
    cols = [c for c in cols_show if c in first]
    if not cols:
        cols = list(first.keys())[:8]

    sorted_rows = sorted(
        df_rows,
        key=lambda r: float(r.get("连板数", 0) or 0),
        reverse=True,
    )[:limit]

    print(f"连板梯队（前 {limit}，列：{' / '.join(cols)}）")
    for r in sorted_rows:
        parts = [str(r.get(c, "") or "—") for c in cols]
        print("  " + " | ".join(parts))


def _build_snapshot_dict(date_yyyymmdd: str) -> Dict[str, Any]:
    zt, dt, height, stock = get_market_data(date_yyyymmdd)
    temp = sentiment_temperature(zt, dt)
    return {
        "ok": True,
        "date": date_yyyymmdd,
        "zt_count": zt,
        "dt_count": dt,
        "temperature_c": round(temp, 2),
        "top_height": height,
        "top_stock": stock,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="A 股情绪切片（与 market-skills API 同源）")
    p.add_argument(
        "--date",
        metavar="YYYYMMDD",
        default=None,
        help="交易日，默认上海时区当天日历日",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="向 stdout 输出一行 JSON（便于 OpenClaw 解析）",
    )
    p.add_argument(
        "--write-feishu",
        action="store_true",
        help="写入飞书情绪表（需 FEISHU_* 与情绪表 table_id，见 .env.example）",
    )
    p.add_argument(
        "--with-llm",
        action="store_true",
        help="与 --write-feishu 同用时：走完整盘后流水线（LLM 生成情绪结论），等同 scripts/daily_quant_cli.py",
    )

    args = p.parse_args()
    raw = (args.date or "").strip()
    if raw:
        if len(raw) != 8 or not raw.isdigit():
            print("错误：--date 须为 8 位 YYYYMMDD", file=sys.stderr)
            return 2
        target = raw
    else:
        target = _today_yyyymmdd_shanghai()

    feishu_result: Optional[Dict[str, Any]] = None

    try:
        zt, dt, height, stock = get_market_data(target)
    except Exception as e:
        print(f"获取数据失败: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({"ok": False, "error": str(e), "date": target}, ensure_ascii=False))
        return 1

    temp = sentiment_temperature(zt, dt)
    pool_rows: List[Dict[str, Any]] = []
    try:
        pool_rows = get_limit_up_pool(target)
    except Exception as e:
        print(f"（涨停池明细拉取失败，仅展示汇总：{e}）", file=sys.stderr)

    # —— 飞书写入（在打印前完成，便于 --json 带上结果）——
    if args.write_feishu:
        if args.with_llm:
            feishu_result = run_post_market_pipeline(target)
        else:
            feishu_result = append_sentiment_openclaw_no_llm(target)

    # —— 人类可读 ——
    if not args.json:
        print(f"正在请求 {target} 的 A 股涨停池（东财 / akshare），与 uvicorn main:app 同源接口数据。")
        print()
        print("=======================")
        print(f"交易日 ({target}) 市场情绪切片")
        print(f"涨停: {zt} 家 | 跌停: {dt} 家 | 情绪温度: {temp:.2f} °C")
        print(f"空间龙: {stock}（{height} 连板）")
        print("=======================")
        print()
        if pool_rows:
            _print_top_limit_up(pool_rows)
        else:
            print("涨停池明细为空。")
        print()
        if zt + dt > 0:
            if temp > 80:
                tip = "情绪高涨，可能是高潮期，注意后市分歧。"
            elif temp < 20:
                tip = "情绪冰点，亏钱效应极大，耐心等待冰点反转的试错机会。"
            else:
                tip = "情绪震荡期，聚焦核心龙头或空仓观望。"
            print(f"💡 结论: {tip}")

        if args.write_feishu and feishu_result is not None:
            print()
            print("—— 飞书 ——")
            print(json.dumps(feishu_result, ensure_ascii=False, indent=2))

    # —— 机器可读 ——
    if args.json:
        out = _build_snapshot_dict(target)
        out["limit_up_top"] = sorted(
            pool_rows,
            key=lambda r: float(r.get("连板数", 0) or 0),
            reverse=True,
        )[:10]
        if feishu_result is not None:
            out["feishu"] = feishu_result
        print(json.dumps(out, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
