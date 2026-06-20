"""
JSON 命令分发层（阶段四 NL / LLM 联调）。

协议见：团队作业/插件命令协议.md
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

import bpy

from .nl_handlers import CommandExecutionError, NL_COMMAND_HANDLERS, HandlerFn

# action 名称 -> handler(context, params) -> (ok, message)
COMMAND_HANDLERS: Dict[str, HandlerFn] = {}


def register_command(action: str, handler: HandlerFn) -> None:
    COMMAND_HANDLERS[action] = handler


def register_default_commands() -> None:
    """注册 P0 阶段全部 action（幂等，register 时调用）。"""
    COMMAND_HANDLERS.clear()
    for action, handler in NL_COMMAND_HANDLERS.items():
        register_command(action, handler)


def list_registered_actions() -> list[str]:
    return sorted(COMMAND_HANDLERS.keys())


def execute_commands(
    context: bpy.types.Context,
    data: dict[str, Any],
) -> Tuple[bool, str, List[str]]:
    """
    执行 commands 列表。

    返回 (全部成功, 汇总 reply, 逐条结果消息)。
    data 格式见 插件命令协议.md。
    """
    if context is None:
        context = bpy.context

    results: List[str] = []
    commands = data.get("commands")
    if not isinstance(commands, list) or not commands:
        reply = str(data.get("reply") or "未包含 commands")
        return False, reply, [f"⚠ {reply}"]

    all_ok = True
    for index, cmd in enumerate(commands):
        if not isinstance(cmd, dict):
            results.append(f"✗ 第 {index + 1} 条命令格式错误")
            all_ok = False
            continue

        action = str(cmd.get("action", "")).strip()
        params = cmd.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            results.append(f"✗ {action or '?'}：params 必须是对象")
            all_ok = False
            continue

        handler = COMMAND_HANDLERS.get(action)
        if handler is None:
            results.append(f"✗ 未注册 action: {action}")
            all_ok = False
            continue

        try:
            ok, message = handler(context, params)
            if ok:
                results.append(f"✔ {action}：{message}")
            else:
                results.append(f"✗ {action}：{message}")
                all_ok = False
        except CommandExecutionError as exc:
            results.append(f"✗ {action}：{exc.message}")
            all_ok = False
        except Exception as exc:
            results.append(f"✗ {action}：{exc}")
            all_ok = False

    reply = str(data.get("reply") or "")
    if not reply and results:
        reply = results[-1].lstrip("✔✗ ").split("：", 1)[-1] if results else ""
    return all_ok, reply, results


def execute_commands_json(
    context: bpy.types.Context,
    payload: dict[str, Any],
) -> Tuple[bool, str, List[str]]:
    """别名，供 nl_execute / 测试脚本调用。"""
    return execute_commands(context, payload)
