"""
大模型复盘：从 daily_quant_bot 抽离，供 15:05 盘后流水线与手动调试复用。
环境变量：SILICONFLOW_API_KEY（与既有脚本一致），可选 OPENAI_API_KEY + OPENAI_BASE_URL。
"""

from __future__ import annotations

import os
from typing import Tuple

from openai import OpenAI

# 默认硅基流动（与 daily_quant_bot 一致）
_DEFAULT_BASE = "https://api.siliconflow.cn/v1"
_DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"


def _client() -> OpenAI:
    key = (
        os.environ.get("SILICONFLOW_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    base = (
        os.environ.get("SILICONFLOW_API_BASE", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or _DEFAULT_BASE
    )
    if not key:
        raise RuntimeError("未配置 SILICONFLOW_API_KEY 或 OPENAI_API_KEY")
    return OpenAI(api_key=key, base_url=base)


def generate_ai_recap(
    date_yyyymmdd: str,
    zt_count: int,
    dt_count: int,
    top_height: int,
    top_stock: str,
) -> str:
    """生成「游资视角」收盘复盘短文（约 200 字）。"""
    model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    prompt = f"""
你是一个深谙 A 股超短线情绪周期的实战派游资大V（风格类似'退哥'）。
你的交易核心是看大做小，通过涨跌停家数、连板高度来判断市场目前处于：主升期、高位震荡期、退潮期，还是极致冰点期。

今日（{date_yyyymmdd}）真实盘面数据如下：
- 涨停家数：{zt_count} 家
- 跌停家数：{dt_count} 家
- 市场最高连板：{top_height} 连板（代表个股：{top_stock}）

请根据以上客观数据，写一份 200 字左右的收盘复盘。
要求：
1. 语气犀利、客观、一针见血。
2. 明确指出当前的情绪周期阶段。
3. 直接给出明天的操作纪律（例如：空仓防守、试错首板、拥抱核心龙头等）。
"""
    client = _client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return (response.choices[0].message.content or "").strip()


def cycle_phase_from_temperature(temp: float) -> Tuple[str, str]:
    """由情绪温度粗略给出周期阶段与备注（与前端 Hero 卡片字段对齐）。"""
    if temp >= 75:
        return "主升 / 亢奋", "涨多跌少，注意一致后的分歧。"
    if temp >= 50:
        return "震荡", "结构性机会，聚焦核心。"
    if temp >= 25:
        return "退潮 / 分歧", "容错下降，控仓为主。"
    return "冰点 / 防守", "亏钱效应扩散，宁可错过。"
