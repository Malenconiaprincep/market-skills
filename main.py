"""
market-skills 全能引擎入口：FastAPI + 后台守护线程（盘中实时 / 盘后飞书+大模型）。

运行：uvicorn main:app --host 0.0.0.0 --port 8787

HTTP 路由见下方 `/api/intraday`、`/api/limit_up`、`/api/limit_down` 等。
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intraday_runner import run_intraday, verify_request_auth  # noqa: E402
from market_sentiment_core import (  # noqa: E402
    get_limit_down_pool,
    get_limit_up_pool,
    get_market_data,
    get_market_data_realtime_spot,
)
from services.alert_engine import evaluate_intraday_alerts  # noqa: E402
from services.llm_service import cycle_phase_from_temperature  # noqa: E402
from services.post_market import (  # noqa: E402
    feishu_history_payload,
    run_post_market_pipeline,
    sentiment_temperature,
)
from shanghai_calendar import in_trading_window, trading_date_str  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("market-skills")

# ---------- 全局状态（盘中实时 + 预警 + 可选历史缓存） ----------
_state_lock = threading.Lock()
GLOBAL_STATE: Dict[str, Any] = {
    "realtime": {
        "temp": 0.0,
        "zt": 0,
        "dt": 0,
        "top_stock": "",
        "top_height": 0,
        "date": "",
        "cycle_phase": "—",
        "cycle_note": "",
        "updated_at": None,
    },
    "alerts": [],
}

# 守护线程内：上一帧盘面、上一成功盘后日期
_prev_realtime: Optional[Dict[str, Any]] = None
_last_post_market_date: Optional[str] = None


def _sh_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _is_weekday_sh() -> bool:
    return _sh_now().weekday() < 5


def _minutes_since_midnight_sh() -> int:
    n = _sh_now()
    return n.hour * 60 + n.minute


def in_post_market_fire_window() -> bool:
    """盘后单次触发窗口：15:05–15:08（工作日），与 60s tick 对齐。"""
    if not _is_weekday_sh():
        return False
    t = _minutes_since_midnight_sh()
    return (15 * 60 + 5) <= t <= (15 * 60 + 8)


def unified_daemon_loop() -> None:
    """
    大一统后台任务：每 60s
    - 盘中：拉 akshare，更新 realtime，追加预警
    - 盘后：在 15:05 窗口触发一次「大模型 + 飞书写表」（内部去重）
    """
    global _prev_realtime, _last_post_market_date
    logger.info("unified_daemon_loop 已启动")

    while True:
        try:
            date_str = trading_date_str()

            # —— 盘后 15:05 分支 ——
            if in_post_market_fire_window() and _last_post_market_date != date_str:
                logger.info("触发盘后流水线：%s", date_str)
                res = run_post_market_pipeline(date_str)
                logger.info("盘后结果：%s", res)
                if res.get("skipped") or res.get("feishu_written") or res.get("ok"):
                    _last_post_market_date = date_str

            # —— 盘中实时分支 ——
            if in_trading_window():
                try:
                    # 涨跌停家数：东财 A 股实时行情 stock_zh_a_spot_em；连板/空间龙仍用当日涨停池
                    zt, dt, height, stock = get_market_data_realtime_spot(date_str)
                except Exception:
                    logger.exception("get_market_data_realtime_spot 失败，回退涨跌停池")
                    try:
                        zt, dt, height, stock = get_market_data(date_str)
                    except Exception:
                        logger.exception("get_market_data 回退失败")
                        time.sleep(60)
                        continue

                temp = sentiment_temperature(zt, dt)
                phase, note = cycle_phase_from_temperature(temp)
                rt = {
                    "temp": round(temp, 2),
                    "zt": zt,
                    "dt": dt,
                    "top_stock": stock,
                    "top_height": int(height),
                    "date": date_str,
                    "cycle_phase": phase,
                    "cycle_note": note,
                    "updated_at": _sh_now().isoformat(),
                }
                new_alerts = evaluate_intraday_alerts(_prev_realtime, rt, date_str)
                with _state_lock:
                    GLOBAL_STATE["realtime"] = rt
                    if new_alerts:
                        merged = list(GLOBAL_STATE["alerts"]) + new_alerts
                        GLOBAL_STATE["alerts"] = merged[-200:]
                _prev_realtime = dict(rt)
            else:
                with _state_lock:
                    GLOBAL_STATE["realtime"]["cycle_note"] = (
                        GLOBAL_STATE["realtime"].get("cycle_note") or "非盘中窗口或休市"
                    )

        except Exception:
            logger.exception("daemon tick 异常")

        time.sleep(60)


def start_daemon_background() -> None:
    t = threading.Thread(target=unified_daemon_loop, name="unified-daemon", daemon=True)
    t.start()


app = FastAPI(title="Market Skills Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    start_daemon_background()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/realtime")
def api_realtime() -> Dict[str, Any]:
    """前端盘中雷达：核心盘口 + 预警列表。"""
    with _state_lock:
        return {
            "ok": True,
            "realtime": dict(GLOBAL_STATE["realtime"]),
            "alerts": list(GLOBAL_STATE["alerts"]),
        }


@app.get("/api/history")
def api_history() -> Dict[str, Any]:
    """
    飞书多维表格最近约 15 天情绪记录（结构与 /api/bitable-records 中 records 对齐）。
    """
    payload, err = feishu_history_payload()
    if err:
        return {"ok": False, "error": err, "records": [], "source": "none"}
    assert payload is not None
    return payload


@app.post("/api/admin/post_market_now")
def admin_post_market_now() -> Dict[str, Any]:
    """手动触发盘后流水线（调试用）。"""
    d = trading_date_str()
    return run_post_market_pipeline(d)


# ---------- 与 market-web 代理使用的 /api/* 路径一致 ----------
def _auth_or_401(request: Request) -> None:
    if not verify_request_auth(request.headers):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _intraday_json_response(out: Dict[str, Any]) -> JSONResponse:
    if out.get("ok"):
        return JSONResponse(out, 200)
    err = str(out.get("error") or "")
    code = 400 if "invalid slot" in err else 500
    return JSONResponse(out, status_code=code)


def _parse_trade_date(date_param: str | None) -> tuple[str | None, str | None]:
    if not date_param or not str(date_param).strip():
        return trading_date_str(), None
    d = str(date_param).strip()
    if len(d) == 8 and d.isdigit():
        return d, None
    return None, "invalid date, use YYYYMMDD"


class IntradaySlotBody(BaseModel):
    slot: str


@app.get("/api/intraday")
def api_intraday_get(request: Request, slot: str | None = Query(None)) -> JSONResponse:
    """GET ?slot=09:40"""
    _auth_or_401(request)
    s = (slot or "").strip()
    if not s:
        return JSONResponse(
            {
                "ok": False,
                "error": "missing slot",
                "hint": "GET /api/intraday?slot=09:40 （或 10:30 / 14:30）",
            },
            400,
        )
    try:
        out = run_intraday(s)
        return _intraday_json_response(out)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)


@app.post("/api/intraday")
def api_intraday_post(request: Request, body: IntradaySlotBody) -> JSONResponse:
    _auth_or_401(request)
    s = (body.slot or "").strip()
    if not s:
        return JSONResponse({"ok": False, "error": "missing slot", "hint": 'POST {"slot":"14:30"}'}, 400)
    try:
        out = run_intraday(s)
        return _intraday_json_response(out)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)


@app.get("/api/limit_up")
def api_limit_up(request: Request, date: str | None = Query(None)) -> JSONResponse:
    _auth_or_401(request)
    d, err = _parse_trade_date(date)
    if err:
        return JSONResponse({"ok": False, "error": err}, 400)
    assert d is not None
    try:
        rows = get_limit_up_pool(d)
        return JSONResponse(  
            {
                "ok": True,
                "date": d,
                "pool": "limit_up",
                "count": len(rows),
                "rows": rows,
            }
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)


@app.get("/api/limit_down")
def api_limit_down(request: Request, date: str | None = Query(None)) -> JSONResponse:
    _auth_or_401(request)
    d, err = _parse_trade_date(date)
    if err:
        return JSONResponse({"ok": False, "error": err}, 400)
    assert d is not None
    try:
        rows = get_limit_down_pool(d)
        return JSONResponse(
            {
                "ok": True,
                "date": d,
                "pool": "limit_down",
                "count": len(rows),
                "rows": rows,
            }
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8787, reload=False)
