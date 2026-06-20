"""
阶段四 P1：自然语言指令执行（离线规则 + command_executor）。
"""

from __future__ import annotations

import bpy

from ..core.city_generator import icity_scene_ready
from ..core.command_executor import execute_commands
from ..core.nl_intent_engine import parse_nl_input
from ..scg_nl_preferences import sync_scene_from_disk


_SOURCE_LABELS = {
    "llm": "LLM",
    "offline_rule": "离线",
    "empty": "",
    "unknown": "未识别",
    "llm_fallback_failed": "LLM失败",
}


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source or "?")


def _set_nl_feedback(
    scene: bpy.types.Scene,
    ok: bool,
    reply: str,
    lines: list[str],
    *,
    source: str = "",
) -> None:
    summary = "；".join(line.lstrip("✔✗ ") for line in lines[:3])
    if len(lines) > 3:
        summary += f" …共 {len(lines)} 条"
    src_tag = f"[{_source_label(source)}]" if source else ""
    status = f"{'成功' if ok else '失败'}{src_tag}：{reply or summary}"
    scene.scg_nl_status = status[:500]
    scene.scg_nl_last_reply = reply[:300] if reply else summary[:300]
    scene.scg_nl_last_source = source


class SCG_OT_execute_nl(bpy.types.Operator):
    bl_idname = "scg.execute_nl"
    bl_label = "执行自然语言指令"
    bl_description = "解析中文指令并调用 SCG 命令（P1 离线；P2 可开 LLM，失败回退离线）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        scene = context.scene
        text = (scene.scg_nl_input_text or "").strip()
        if not text:
            self.report({"WARNING"}, "请输入自然语言指令")
            scene.scg_nl_status = "失败：输入为空"
            return {"CANCELLED"}

        use_llm = bool(getattr(scene, "scg_use_llm", False))
        if use_llm:
            sync_scene_from_disk(scene)
        payload = parse_nl_input(text, use_llm=use_llm)

        source = str(payload.get("source") or "")

        if not payload.get("commands"):
            reply = payload.get("reply", "无法理解指令")
            _set_nl_feedback(scene, False, reply, [], source=source)
            self.report({"WARNING"}, reply)
            return {"CANCELLED"}

        if use_llm:
            self.report({"INFO"}, f"解析来源：{_source_label(source)}")

        ok, reply, lines = execute_commands(context, payload)
        exec_reply = str(payload.get("reply") or reply)
        _set_nl_feedback(scene, ok, exec_reply, lines, source=source)

        for line in lines:
            if line.startswith("✔"):
                self.report({"INFO"}, line.lstrip("✔ ").strip())
            elif line.startswith("✗"):
                self.report({"ERROR"}, line.lstrip("✗ ").strip())

        if ok:
            return {"FINISHED"}
        self.report({"WARNING"}, scene.scg_nl_status)
        return {"CANCELLED"}


class SCG_OT_save_nl_api_settings(bpy.types.Operator):
    bl_idname = "scg.save_nl_api_settings"
    bl_label = "保存 LLM 设置到本地"
    bl_description = "将 API Key 等写入 Blender 配置目录，重启后自动加载"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..scg_nl_preferences import persist_scene_settings

        path = persist_scene_settings(context.scene)
        self.report({"INFO"}, f"LLM 设置已保存：{path}")
        return {"FINISHED"}


classes = (SCG_OT_execute_nl, SCG_OT_save_nl_api_settings)
