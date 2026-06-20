"""
阶段二 Day 7-8：应用 templates.json 模板（验收 A5）。
"""

from __future__ import annotations

import bpy

from ..core.city_generator import icity_scene_ready
from ..core.template_manager import apply_template, format_template_summary, get_template


class SCG_OT_apply_template(bpy.types.Operator):
    bl_idname = "scg.apply_template"
    bl_label = "应用模板"
    bl_description = "按 templates.json 配置树/路/椅/密度/环境并生成城市（不替换 ICity 默认路灯）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        template_id = str(context.scene.scg_template_id)
        if get_template(template_id) is None:
            self.report({"ERROR"}, f"模板 {template_id} 不存在")
            return {"CANCELLED"}
        ok, message = apply_template(context, template_id)
        if ok:
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


classes = (SCG_OT_apply_template,)
