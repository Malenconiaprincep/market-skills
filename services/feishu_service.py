"""
飞书多维表格：使用 HTTP 调用开放平台（与 market-web 中 feishuBitable.js 行为一致）。
亦可后续换为 lark_oapi SDK 的 Request 封装，请求体不变。

情绪表列名需与前端 SENTIMENT_FIELD_NAMES 一致：日期、涨停数、跌停数、情绪温度、情绪结论、空间龙、空间龙连板
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

# 与前端 map 后的内部字段名一致（便于 /api/history 直接给 React 用）
SENTIMENT_INTERNAL = {
    "日期": "date",
    "涨停数": "zt_count",
    "跌停数": "dt_count",
    "情绪温度": "temperature",
    "情绪结论": "ai_recap_text",
    "空间龙": "top_stock",
    "空间龙连板": "top_height",
}

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"


def _tenant_token() -> str:
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET")
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            TOKEN_URL,
            json={"app_id": app_id, "app_secret": app_secret},
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg") or "tenant_access_token 失败")
    return str(data["tenant_access_token"])


def _base_bitable(app_token: str, table_id: str) -> str:
    return (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}"
    )


def _list_all_records(token: str, app_token: str, table_id: str) -> List[Dict[str, Any]]:
    """分页拉取记录（对齐前端 fetchAllBitableRecords）。"""
    out: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    base = _base_bitable(app_token, table_id) + "/records"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=60.0) as client:
        for _ in range(50):
            params: Dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            r = client.get(base, params=params, headers=headers)
            r.raise_for_status()
            body = r.json()
            if body.get("code") != 0:
                raise RuntimeError(body.get("msg") or "list records 失败")
            data = body.get("data") or {}
            items = data.get("items") or []
            out.extend(items)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
    return out


def _list_all_fields(token: str, app_token: str, table_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    base = _base_bitable(app_token, table_id) + "/fields"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=60.0) as client:
        for _ in range(20):
            params: Dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            r = client.get(base, params=params, headers=headers)
            r.raise_for_status()
            body = r.json()
            if body.get("code") != 0:
                raise RuntimeError(body.get("msg") or "list fields 失败")
            data = body.get("data") or {}
            items = data.get("items") or []
            out.extend(items)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
    return out


def _field_name_to_id_map(field_items: List[Dict[str, Any]]) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for f in field_items:
        name = str(f.get("field_name") or f.get("name") or "").strip()
        fid = f.get("field_id")
        if name and fid:
            m[name] = str(fid)
    return m


def _normalize_cell(val: Any) -> Any:
    """粗粒度归一化，对齐 JS normalizeFeishuCellValue。"""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, dict) and "text" in first:
            return "".join(
                str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in val
            )
        return val[0]
    if isinstance(val, dict):
        if "text" in val:
            return val.get("text")
        if "link" in val:
            return val.get("link")
    return str(val)


def _map_record_fields(
    raw_fields: Dict[str, Any],
    name_to_id: Dict[str, str],
) -> Dict[str, Any]:
    """field_id 与中文列名 → 内部字段名。"""
    flat: Dict[str, Any] = {}
    for k, v in (raw_fields or {}).items():
        flat[k] = _normalize_cell(v)
    out: Dict[str, Any] = {}
    id_to_internal = {}
    for cn, internal in SENTIMENT_INTERNAL.items():
        fid = name_to_id.get(cn)
        if fid:
            id_to_internal[fid] = internal
    for fid, internal in id_to_internal.items():
        if fid in flat and flat[fid] is not None:
            out[internal] = flat[fid]
    for cn, internal in SENTIMENT_INTERNAL.items():
        if cn in flat and out.get(internal) is None:
            out[internal] = flat[cn]
    return out


def _finalize_sentiment_row(fields: Dict[str, Any], created_time: Optional[int]) -> Dict[str, Any]:
    """对齐 finalizeSentimentFields 的简化版。"""
    o = dict(fields)
    for k in ("temperature", "zt_count", "dt_count", "top_height"):
        if o.get(k) not in (None, ""):
            try:
                o[k] = float(o[k]) if k == "temperature" else int(float(o[k]))
            except (TypeError, ValueError):
                pass
    if o.get("ai_recap_text") is None:
        o["ai_recap_text"] = ""
    if not o.get("cycle_phase"):
        o["cycle_phase"] = "—"
    if not o.get("cycle_note"):
        o["cycle_note"] = ""
    if not o.get("date") and created_time:
        # 与前端类似：用创建时间兜底
        from datetime import datetime, timezone

        try:
            ms = int(created_time) * 1000 if created_time < 1e12 else int(created_time)
            d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            o["date"] = d.strftime("%Y-%m-%d")
        except Exception:
            pass
    return o


def fetch_sentiment_history_for_dashboard(
    days: int = 15,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    从情绪表读取最近若干条，映射为前端 records 结构：
    [{ "record_id", "fields": { date, zt_count, ... } }, ...]
    按日期降序，最多 days 个自然日跨度（简单按条数截断前 50 条再筛选也可）。
    """
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID", "").strip()
    if not app_token or not table_id:
        return [], "未配置 FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_TABLE_ID"

    token = _tenant_token()
    fields_meta = _list_all_fields(token, app_token, table_id)
    name_to_id = _field_name_to_id_map(fields_meta)
    items = _list_all_records(token, app_token, table_id)

    mapped: List[Dict[str, Any]] = []
    for item in items:
        rid = item.get("record_id") or ""
        raw = item.get("fields") or {}
        created = item.get("created_time")
        f = _map_record_fields(raw, name_to_id)
        f = _finalize_sentiment_row(f, created)
        mapped.append({"record_id": rid, "fields": f})

    def sort_key(x: Dict[str, Any]) -> str:
        return str(x.get("fields", {}).get("date") or "")

    mapped.sort(key=sort_key, reverse=True)
    # 取最近 days 条（表通常按日一行）
    return mapped[: max(days, 1)], None


def _feishu_field_value_for_type(
    field_type: Optional[int], value: Any, field_name: str
) -> Any:
    """按字段类型包装写入值（飞书 bitable 字段类型见开放平台文档）。"""
    # 常见：1 多行/单行文本 2 数字 5 日期 15 超链接… 不同租户略有差异；文本类优先直传字符串
    t = field_type if field_type is not None else -1
    if t in (1, 3, 18) or field_name in ("情绪结论", "空间龙"):
        return str(value) if value is not None else ""
    if t == 2 or field_name in ("涨停数", "跌停数", "情绪温度", "空间龙连板"):
        try:
            return int(value) if field_name != "情绪温度" else float(value)
        except (TypeError, ValueError):
            return 0
    if t == 5 or field_name == "日期":
        # 日期字段：毫秒时间戳
        from datetime import datetime

        s = str(value).strip()
        if len(s) == 10 and s[4] == "-":
            dt = datetime.strptime(s, "%Y-%m-%d")
            return int(dt.timestamp() * 1000)
        if len(s) == 8 and s.isdigit():
            dt = datetime.strptime(s, "%Y%m%d")
            return int(dt.timestamp() * 1000)
        return value
    return value


def append_sentiment_row(
    *,
    date_display: str,
    zt_count: int,
    dt_count: int,
    temperature: float,
    ai_recap_text: str,
    top_stock: str,
    top_height: int,
) -> Tuple[bool, Optional[str]]:
    """
    追加一行情绪复盘到飞书表。列名需与多维表格中文列一致。
    返回 (ok, error_message)
    """
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID", "").strip()
    if not app_token or not table_id:
        return False, "未配置飞书表"

    token = _tenant_token()
    field_items = _list_all_fields(token, app_token, table_id)
    name_to_id = _field_name_to_id_map(field_items)
    type_by_id = {
        str(f.get("field_id")): f.get("type") for f in field_items if f.get("field_id")
    }

    internal_to_feishu = {
        "date": "日期",
        "zt_count": "涨停数",
        "dt_count": "跌停数",
        "temperature": "情绪温度",
        "ai_recap_text": "情绪结论",
        "top_stock": "空间龙",
        "top_height": "空间龙连板",
    }
    payload_row = {
        "date": date_display,
        "zt_count": zt_count,
        "dt_count": dt_count,
        "temperature": round(temperature, 2),
        "ai_recap_text": ai_recap_text,
        "top_stock": top_stock,
        "top_height": top_height,
    }

    fields_payload: Dict[str, Any] = {}
    for internal, cn in internal_to_feishu.items():
        fid = name_to_id.get(cn)
        if not fid:
            continue
        val = payload_row.get(internal)
        ft = type_by_id.get(fid)
        fields_payload[fid] = _feishu_field_value_for_type(ft, val, cn)

    url = _base_bitable(app_token, table_id) + "/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, json={"fields": fields_payload}, headers=headers)
        try:
            body = r.json()
        except Exception:
            body = {}
        if r.status_code >= 400 or body.get("code") not in (0, None):
            return False, body.get("msg") or r.text[:300]
    return True, None
