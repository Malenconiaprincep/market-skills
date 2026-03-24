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

### Vercel 部署（无长驻进程）

仓库含 **`vercel.json`** + **`api/index.py`**（Mangum 挂载 FastAPI）。在项目根连接 Vercel 后：

1. **环境变量**：在 Vercel 控制台配置 `.env.example` 中需要的项（飞书、密钥等）；`VERCEL=1` 由平台自动注入，会**跳过** `unified_daemon_loop`（无 60s 后台线程）。
2. **访问路径**：根路径 **`/`** 会返回服务说明（勿再以「未配置路由」误判为挂掉）；健康检查 **`/health`**；业务接口仍为 **`/api/realtime`**、`/api/history` 等。
3. **`market-web`**：将 `MARKET_SKILLS_API_BASE` 设为 `https://<你的项目>.vercel.app`（无尾部斜杠）。
4. **限制**：盘中轮询守护、强预警依赖**常驻进程**，Vercel 上仅适合「按需 HTTP」；完整引擎请用 **Docker / Railway / Render** 跑 `uvicorn main:app`。

若仍见 **`{"detail":"Not Found"}`**：多半是请求了**未注册的路径**（仅 `/`、`/health`、`/docs`、`/api/*` 等可用），或 **未用本仓库的 `vercel.json` 重写**导致请求未进到 `api/index.py`。
