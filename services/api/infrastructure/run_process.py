import json
import math
from typing import Any

TOOL_LABELS = {
    "read_career_context": "读取职业背景",
    "read_career_note": "读取规则与笔记",
    "read_material": "读取材料",
    "list_materials": "查找材料",
    "propose_material_edit": "提出材料修改",
    "propose_new_material": "创作材料草稿",
    "propose_career_rule": "提出候选规则",
    "search_public_web": "检索公开网页",
    "read_main_chat": "读取主线参考",
}


def safe_duration(value: Any) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
        else None
    )


def tool_activity(tool: Any, run_status: str) -> dict[str, object]:
    duration = safe_duration(getattr(getattr(tool, "metrics", None), "duration", None))
    result = getattr(tool, "result", None)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = None
    outcome = result.get("status") if isinstance(result, dict) else None
    if not isinstance(outcome, str):
        outcome = None
    if getattr(tool, "tool_call_error", False) or outcome in {
        "unavailable",
        "error",
        "failed",
        "conflict",
    }:
        status = "ERROR"
    elif outcome in {"rejected", "denied"}:
        status = "REJECTED"
    elif getattr(tool, "result", None) is not None or duration is not None:
        status = "COMPLETED"
    elif getattr(tool, "is_paused", False):
        status = "PAUSED"
    else:
        status = run_status if run_status in {"RUNNING", "PENDING", "CANCELLED"} else "UNKNOWN"
    return {
        "id": str(getattr(tool, "tool_call_id", None) or "tool"),
        "kind": "tool",
        "label": TOOL_LABELS.get(str(getattr(tool, "tool_name", "")), "工具调用"),
        "status": status,
        "duration_seconds": duration,
    }


def run_process(
    run: Any, final_message_id: str | None, status: str
) -> tuple[dict[str, object], ...]:
    tools = {tool.tool_call_id: tool for tool in (getattr(run, "tools", None) or [])}
    result: list[dict[str, object]] = []
    for message in getattr(run, "messages", None) or []:
        if message.role != "assistant" or message.from_history:
            continue
        content = message.get_content_string()
        if message.id != final_message_id and content:
            result.append({"id": message.id, "kind": "message", "content": content})
        for call in message.tool_calls or []:
            tool = tools.pop(call.get("id"), None)
            if tool is not None:
                result.append(tool_activity(tool, status))
    result.extend(tool_activity(tool, status) for tool in tools.values())
    return tuple(result)
