"""
安全调用 ICity 原有 Operator（避免未 Start 时 KeyError）。
"""

from __future__ import annotations

import bpy

from ..core.city_generator import enter_icity_edit_mode, icity_base_exists, icity_collection_exists


class SCG_OT_edit_city(bpy.types.Operator):
    """在 ICity Base 已存在时进入 Edit City（未 Start 时不可用）。"""

    bl_idname = "scg.edit_city"
    bl_label = "Edit City"
    bl_description = "调用 ICity Edit City；需先执行 Start"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_base_exists()

    def execute(self, context):
        if not icity_base_exists():
            self.report({"WARNING"}, "请先点击 Start 初始化城市场景")
            return {"CANCELLED"}
        enter_icity_edit_mode(context)
        return {"FINISHED"}


class SCG_OT_start_icity(bpy.types.Operator):
    """转发 ICity Start（与 ICity editor 未初始化时行为一致）。"""

    bl_idname = "scg.start_icity"
    bl_label = "Start"
    bl_description = "调用 ICity Start，追加初始化场景"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return not icity_collection_exists()

    def invoke(self, context, event):
        return bpy.ops.sna.start_5209e("INVOKE_DEFAULT")


classes = (
    SCG_OT_edit_city,
    SCG_OT_start_icity,
)
