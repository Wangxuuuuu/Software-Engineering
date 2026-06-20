"""
阶段二 Day 5-6：单独应用道路纹理（无需重新生成整城）。
"""

from __future__ import annotations

import bpy

from ..core.city_generator import (
    _flush_viewport_refresh,
    _type_enum_to_index,
    icity_scene_ready,
    set_road_texture,
)


class SCG_OT_apply_road_texture(bpy.types.Operator):
    bl_idname = "scg.apply_road_texture"
    bl_label = "应用道路纹理"
    bl_description = "按面板「道路类型」将团队贴图写入 Road 2 材质"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        scene = context.scene
        type_id = _type_enum_to_index(scene.scg_road_type) + 1
        ok, message = set_road_texture(type_id)
        if ok:
            _flush_viewport_refresh()
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


classes = (SCG_OT_apply_road_texture,)
