# market-skills

A 股情绪相关后端：**一个推荐入口**即可跑齐 HTTP + 后台任务。

## 推荐启动（唯一需要记的）

```bash
cd market-skills
pip install -r requirements.txt
# 配置 .env（见 .env.example）
uvicorn main:app --host 0.0.0.0 --port 8787
```

- 文档与调试：<http://127.0.0.1:8787/docs>
- 健康检查：`GET /health`

`main.py` 已包含：

| 路径 | 说明 |
|------|------|
| `GET /api/realtime` | 盘中实时 + 预警（涨跌停家数：`stock_zh_a_spot_em`；连板/空间龙：当日涨停池） |
| `GET /api/history` | 飞书情绪表历史 |
| `GET/POST /api/intraday` | 盘中快照（槽位 09:40/10:30/14:30）：连续竞价内用 `stock_zh_a_spot_em`；**收盘后**优先读 Upstash 落库快照，否则为东财**日终池**口径（见响应 `snapshot_mode` / `hint`） |
| `GET /api/limit_up` `GET /api/limit_down` | 涨跌停池 |
| `POST /api/admin/post_market_now` | 手动盘后流水线 |

鉴权：请求头 `Authorization: Bearer <INTRADAY_API_SECRET>`（未配置环境变量时不校验，仅本地调试用）。

## 目录说明（为何有这些文件）

| 路径 | 作用 |
|------|------|
| **`main.py`** | **主入口**：FastAPI + 守护线程 + 上表全部路由 |
| **`market_sentiment_core.py`** | akshare 拉取涨跌停、情绪温度等核心数据 |
| **`shanghai_calendar.py`** | 上海时区交易日字符串 |
| **`services/`** | 大模型复盘、飞书写表、盘后流水线、盘中启发式预警 |
| **`intraday_runner.py`** | `/api/intraday` 调用的「单次盘中任务」+ 鉴权；含 14:30 冰点预警、Upstash 快照 |
| **`intraday_alerts.py`**、**`intraday_state.py`** | 仅被 `intraday_runner` 使用（跨槽位对比、Redis） |
| **`scripts/daily_quant_cli.py`** | 命令行跑一次盘后流水线（与 `POST /api/admin/post_market_now` 等价） |
| **`market_sentiment.py`** | **OpenClaw**：与 `market_sentiment_core` / `GET /api/limit_up` 同源；支持 `--json`、`--write-feishu`（仅盘面或 `--with-llm` 完整盘后）写入飞书情绪表 |
| **`daily_quant_bot.py`** | **独立脚本**：拉数据 + 调大模型生成复盘正文，stdout 供 OpenClaw 写入飞书；与 `services/llm_service.py` 并存（服务内用后者，编排用本脚本） |
## 与 market-web 联调

`market-web` 的 `MARKET_SKILLS_API_BASE` 指向上述 `uvicorn` 地址即可。

云端部署若需 **Vercel** 等，请自行用 **Docker / 容器** 跑 `uvicorn main:app`，本仓库已不再提供 `api/*.py` 无框架 Serverless 入口。
