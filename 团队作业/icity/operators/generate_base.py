"""
一键「生成基础城市」— Day 2-3：按面板参数写入 Attribute 并刷新场景。
"""

from __future__ import annotations

import bpy

from ..core.city_generator import enter_icity_edit_mode, generate_base_city_from_scene


class SCG_OT_generate_base_city(bpy.types.Operator):
    bl_idname = "scg.generate_base_city"
    bl_label = "生成基础城市"
    bl_description = "在 Object 模式写入 Attribute 并刷新；不会切换退出 Edit（与 ICity Edit 不同）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.view_layer is not None

    def execute(self, context):
        scene = context.scene
        ok, message = generate_base_city_from_scene(scene, context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        if getattr(scene, "scg_enter_edit_after_generate", False):
            enter_icity_edit_mode(context)

        self.report({"INFO"}, message)
        return {"FINISHED"}


classes = (SCG_OT_generate_base_city,)
