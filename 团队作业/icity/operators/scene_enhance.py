"""
阶段三：场景增强 Operator（生态山水；动态元素在阶段 C 扩展）。
"""

from __future__ import annotations

import bpy

from ..core.assets_manager import lake_landscape_asset_available
from ..core.city_generator import icity_scene_ready
from ..core.scene_enhance import add_landscape_surround, cleanup_landscape_surround


class SCG_OT_add_landscape_surround(bpy.types.Operator):
    bl_idname = "scg.add_landscape_surround"
    bl_label = "添加中央山水"
    bl_description = (
        "从 lake/LowPolyTrees.blend 追加单块放大山水，"
        "城市位于水面中央（验收 A8 生态元素）"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        if not lake_landscape_asset_available():
            self.report({"ERROR"}, "未找到 lake/LowPolyTrees.blend")
            return {"CANCELLED"}
        ok, message = add_landscape_surround(context)
        if ok:
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"WARNING"}, message)
        return {"CANCELLED"}


class SCG_OT_remove_landscape_surround(bpy.types.Operator):
    bl_idname = "scg.remove_landscape_surround"
    bl_label = "清除山水环境"
    bl_description = (
        "移除中央山水及 SCG_Ecology 内生态对象（含后续船只等），"
        "不残留游标/城心处的缩小网格"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        cleanup_landscape_surround(context)
        self.report({"INFO"}, "已清除山水环境，可重新点击「添加中央山水」")
        return {"FINISHED"}


classes = (
    SCG_OT_add_landscape_surround,
    SCG_OT_remove_landscape_surround,
)
