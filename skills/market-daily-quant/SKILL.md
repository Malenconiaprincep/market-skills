---
name: market-daily-quant
description: 在本仓库根目录执行 daily_quant_bot.py，拉取 A 股涨跌停与连板数据并经硅基流动模型生成复盘；结果打印到 stdout，便于飞书等渠道转发。
user-invocable: true
metadata:
  {
    "openclaw": {
      "emoji": "📈",
      "requires": { "bins": ["python3"] },
      "homepage": "https://cloud.siliconflow.cn"
    }
  }
---

# A 股日度情绪复盘（market-daily-quant）

## 何时使用

用户要求「跑日复盘」「情绪复盘」「daily quant」「执行 daily_quant_bot」等，或需要把当日 A 股涨停/跌停/空间龙摘要 + AI 复盘发到飞书时：用 **Exec** 运行脚本，**不要**把 `daily_quant_bot.py` 全文贴进对话。

## 前置条件

1. **工作区**：OpenClaw Agent 的工作区根目录必须是本 **`market` 仓库根目录**（与 `skills/`、`daily_quant_bot.py` 同级）。若在另一台机器跑 OpenClaw，请在该机上 `git clone` / `git pull` 本仓库并保持路径一致。
2. **Python**：`python3` 在 PATH 中；已安装依赖，至少包括：`akshare`、`openai`（及 pandas 等 akshare 常用依赖）。示例：`python3 -m pip install akshare openai pandas`。
3. **大模型**：脚本使用硅基流动 `https://api.siliconflow.cn/v1` 与模型 `Qwen/Qwen2.5-7B-Instruct`。执行前必须设置环境变量 **`SILICONFLOW_API_KEY`**（勿写入仓库、勿贴进聊天）；OpenClaw 可在 `skills.entries` 或网关环境中注入。

## 执行方式（优先）

使用 **Exec**：

- **workdir**：工作区根目录（包含 `daily_quant_bot.py` 的目录）。
- **command**：`python3 daily_quant_bot.py`

无需额外参数即可运行。脚本内 `TODAY` 默认为测试用日期字符串；若需「当天」交易日，应先在仓库中把 `daily_quant_bot.py` 里 `TODAY` 改为 `datetime.now().strftime("%Y%m%d")` 并 `from datetime import datetime`（或改为读命令行参数），再执行。

## 输出说明

- 成功时：**标准输出**为多行文本（标题、涨跌停与温度、分隔线、AI 复盘正文）。
- 对接飞书：由 OpenClaw 飞书渠道或后续节点将 **stdout 全文**作为消息内容发送即可。
- 若输出为「今日数据为空」：可能非交易日或数据源异常，勿当作模型故障。

## 关于 `{baseDir}`

`{baseDir}` 指向本 Skill 目录 `skills/market-daily-quant/`。脚本位于**工作区根目录**，相对路径为：`{baseDir}/../../daily_quant_bot.py`。执行时仍以**工作区根**为 `workdir` 运行 `python3 daily_quant_bot.py` 最稳妥。

## 安装到 OpenClaw

- **推荐**：整个仓库作为工作区时，本文件已在 `skills/market-daily-quant/SKILL.md`，网关加载工作区后会自动参与 Skills 列表（具体以 OpenClaw 版本为准）。
- **仅拷贝 Skill**：可将 `skills/market-daily-quant/` 复制到另一台机 OpenClaw 工作区的 `skills/` 下，但必须**同时**在该工作区根目录放置（或同步）`daily_quant_bot.py`，否则 Exec 找不到脚本。

更多见 OpenClaw 文档：[Skills](https://docs.openclaw.ai/tools/skills)、[Exec](https://docs.openclaw.ai/tools/exec)。
