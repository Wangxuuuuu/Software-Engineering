"""
自然语言 → commands JSON（阶段四 P1：离线规则；P2 接入 LLM）。

输出格式与 团队作业/插件命令协议.md 一致。
"""

from __future__ import annotations

import re
from typing import Any, Optional

_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _extract_int(text: str, default: Optional[int] = None) -> Optional[int]:
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    for key, value in _CN_DIGIT.items():
        if key in text:
            return value
    return default


def _payload(
    text: str,
    commands: list[dict[str, Any]],
    reply: str,
    *,
    source: str = "offline_rule",
) -> dict[str, Any]:
    return {
        "source": source,
        "raw_text": text,
        "commands": commands,
        "reply": reply,
    }


def offline_parse(text: str) -> Optional[dict[str, Any]]:
    """离线规则解析；无法识别时返回 None。"""
    text = (text or "").strip()
    if not text:
        return None

    normalized = text.replace(" ", "")

    # ── 树 / 路 / 椅 均类型 N ──
    if re.search(r"(树木|树).*(道路|路).*(座椅|椅|长椅)", normalized):
        type_id = _extract_int(normalized, 1)
        return _payload(
            text,
            [{
                "action": "apply_asset_config",
                "params": {
                    "tree_type": type_id,
                    "road_texture": type_id,
                    "bench_type": type_id,
                    "regenerate": True,
                },
            }],
            f"已将树木、道路和座椅设为类型 {type_id}",
        )

    # ── 应用模板 N ──
    match_tpl = re.search(r"(?:应用|使用|切换(?:到)?)?模板\s*(\d+)", normalized)
    if match_tpl:
        tid = match_tpl.group(1)
        return _payload(
            text,
            [{"action": "apply_template", "params": {"template_id": tid}}],
            f"已应用模板 {tid}",
        )

    # ── 道路类型 N ──
    match_road = re.search(
        r"(?:道路|路面|马路).*(?:改为|换成|设为|设置成?|用)?类型\s*(\d+)",
        normalized,
    )
    if not match_road:
        match_road = re.search(r"道路类型\s*(\d+)", normalized)
    if match_road:
        road_type = int(match_road.group(1))
        return _payload(
            text,
            [{"action": "set_road_texture", "params": {"type": road_type}}],
            f"已将道路改为类型 {road_type}",
        )

    # ── 添加 N 辆车辆 ──
    match_car = re.search(
        r"添加\s*(\d+|[一二三四五六七八九十两]+)\s*辆?\s*车",
        text,
    )
    if match_car:
        count = _extract_int(match_car.group(1), 2) or 2
    elif re.search(r"添加\s*车", normalized):
        count = 2
    else:
        count = None
    if count is not None:
        return _payload(
            text,
            [{"action": "add_dynamic_element", "params": {"type": "car", "count": count}}],
            f"已添加 {count} 辆车辆",
        )

    # ── 雨天（方案 A）──
    if re.search(r"(雨天|下雨|降雨|切换到?雨天)", normalized):
        return _payload(
            text,
            [{"action": "set_environment", "params": {"mode": "rainy"}}],
            "已切换雨天模式（环境变暗；雨粒子待阶段二扩展）",
        )

    # ── 白天 ──
    if re.search(r"(天色)?(变为|切换(到)?|恢复)?白天|天亮|变亮", normalized):
        return _payload(
            text,
            [{"action": "set_environment", "params": {"mode": "day"}}],
            "已切换白天环境",
        )

    # ── 夜间 / 变暗 ──
    if re.search(r"(天色)?变暗|天黑|夜间|夜晚|切换(到)?夜间|入夜", normalized):
        return _payload(
            text,
            [{"action": "set_environment", "params": {"mode": "night"}}],
            "已切换夜间环境",
        )

    return None


def parse_nl_input(text: str, use_llm: bool = False) -> dict[str, Any]:
    """
    统一解析入口：P1 默认离线；use_llm=True 时优先 LLM，失败回退离线。
    """
    text = (text or "").strip()
    if not text:
        return _payload(text, [], "请输入指令", source="empty")

    llm_error: str | None = None

    if use_llm:
        try:
            from .nl_llm_backend import call_llm_and_to_payload

            llm_result = call_llm_and_to_payload(text)
            if llm_result and llm_result.get("commands"):
                return llm_result
            llm_error = str(llm_result.get("reply") or "LLM 未返回 commands")
        except ImportError:
            llm_error = "LLM 模块未安装"
        except Exception as exc:
            llm_error = str(exc)
            print(f"[SCG NL] LLM 失败，回退离线: {exc}")

    offline = offline_parse(text)
    if offline:
        if llm_error:
            offline = dict(offline)
            offline["reply"] = f"{offline.get('reply', '')}（LLM 回退：{llm_error[:80]}）"
        return offline

    if llm_error:
        return _payload(text, [], f"LLM 失败且离线无法识别：{llm_error}", source="llm_fallback_failed")

    return _payload(text, [], f"无法理解指令：{text}", source="unknown")
