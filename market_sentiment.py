import akshare as ak
import pandas as pd

# 目标：获取 2026 年 3 月 23 日的涨停板数据
target_date = "20260323" 

print(f"正在向服务器请求 {target_date} 的 A 股涨停数据，请稍候...")

try:
    # 调用 AkShare 接口获取东方财富的涨停池数据
    df_limit_up = ak.stock_zt_pool_em(date=target_date)
    
    if not df_limit_up.empty:
        total_zt = len(df_limit_up)
        print(f"\n=======================")
        print(f"今日 ({target_date}) 市场情绪切片:")
        print(f"全市场涨停总家数: {total_zt} 家")
        print(f"=======================\n")
        
        # 筛选出我们最关心的字段：代码、名称、涨跌幅、最新价和连板数
        columns_to_show = ['代码', '名称', '涨跌幅', '最新价', '连板数']
        
        # 按照“连板数”从高到低排序，看看今天的“市场空间龙”是谁
        df_sorted = df_limit_up.sort_values(by='连板数', ascending=False)
        
        print("今日连板高度梯队 (前 10 名)：")
        print(df_sorted[columns_to_show].head(10).to_string(index=False))
        
    else:
        print("获取到的数据为空，请检查是否为交易日，或稍后再试。")

    # 接着获取今日的跌停板数据 (注意：接口名是 dtgc 跌停股池)
    df_limit_down = ak.stock_zt_pool_dtgc_em(date=target_date)
    total_dt = len(df_limit_down) if not df_limit_down.empty else 0
    
    print(f"\n今日跌停总家数: {total_dt} 家")
    
    # 计算极简“情绪温度”指标 (涨停数 / (涨停数 + 跌停数))
    if total_zt + total_dt > 0:
        sentiment_score = (total_zt / (total_zt + total_dt)) * 100
        print(f"🌡️ 今日市场情绪温度: {sentiment_score:.2f} °C")
        
        # 极简策略逻辑判断
        if sentiment_score > 80:
            print("💡 结论: 情绪高涨，可能是高潮期，注意后市分歧。")
        elif sentiment_score < 20:
            print("💡 结论: 情绪冰点，亏钱效应极大，耐心等待冰点反转的试错机会。")
        else:
            print("💡 结论: 情绪震荡期，聚焦核心龙头或空仓观望。")

except Exception as e:
    print(f"获取数据失败，错误信息: {e}")