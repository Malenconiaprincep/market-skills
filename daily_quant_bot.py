import os

from openai import OpenAI

from market_sentiment_core import get_market_data

# ================= ⚙️ 配置区 =================
# 硅基流动 Key：仅通过环境变量注入，勿写入仓库。本地示例：export SILICONFLOW_API_KEY="sk-..."
LLM_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "").strip()
LLM_BASE_URL = "https://api.siliconflow.cn/v1"
LLM_MODEL = "Qwen/Qwen2.5-7B-Instruct"
# 输出到 stdout，供 OpenClaw 等编排后对接飞书等渠道
# =================================================================

def fetch_market_data_safe(target_date):
    """抓取 A 股情绪核心数据；失败时打印原因并返回零值。"""
    print(f"📊 正在获取 {target_date} A 股真实盘面数据...")
    try:
        return get_market_data(target_date)
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        return 0, 0, 0, "错误"

def generate_ai_report(date, zt_count, dt_count, top_height, top_stock):
    """调用大模型生成退哥风格的游资复盘"""
    print("🧠 正在呼叫 AI 大脑生成复盘策略...")
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    
    prompt = f"""
    你是一个深谙 A 股超短线情绪周期的实战派游资大V（风格类似'退哥'）。
    你的交易核心是看大做小，通过涨跌停家数、连板高度来判断市场目前处于：主升期、高位震荡期、退潮期，还是极致冰点期。
    
    今日（{date}）真实盘面数据如下：
    - 涨停家数：{zt_count} 家
    - 跌停家数：{dt_count} 家
    - 市场最高连板：{top_height} 连板（代表个股：{top_stock}）
    
    请根据以上客观数据，写一份 200 字左右的收盘复盘。
    要求：
    1. 语气犀利、客观、一针见血。
    2. 明确指出当前的情绪周期阶段。
    3. 直接给出明天的操作纪律（例如：空仓防守、试错首板、拥抱核心龙头等）。
    """
    
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7 # 稍微带点发散性，让复盘不死板
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ AI 生成失败: {e}")
        return "AI 复盘生成失败，请检查 API 配置。"

if __name__ == "__main__":
    if not LLM_API_KEY:
        print("❌ 未设置环境变量 SILICONFLOW_API_KEY（硅基流动 API Key）。推送 GitHub 前请勿把 Key 写进代码。")
        raise SystemExit(1)

    # 目标交易日 YYYYMMDD；需要当天可改为 datetime.now().strftime("%Y%m%d") 并 from datetime import datetime
    TODAY = "20260324"

    zt, dt, height, stock = fetch_market_data_safe(TODAY)
    if zt > 0 or dt > 0:
        report = generate_ai_report(TODAY, zt, dt, height, stock)
        temp = (zt / (zt + dt)) * 100 if (zt + dt) > 0 else 0.0
        print(f"## A 股情绪复盘 ({TODAY})")
        print(
            f"涨停: {zt} 家 | 跌停: {dt} 家 | 情绪温度: {temp:.1f}% | "
            f"空间龙: {stock} ({height}连板)"
        )
        print("---")
        print(report)
    else:
        print("⚠️ 今日数据为空，可能非交易日或接口异常。")