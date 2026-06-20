"""
阶段二 Day 6-7：应用团队路灯（验收 A4）。
"""

from __future__ import annotations

import bpy

from ..core.city_generator import icity_scene_ready
from ..core.street_lights import apply_street_lights, street_lamp_asset_available


class SCG_OT_apply_street_lights(bpy.types.Operator):
    bl_idname = "scg.apply_street_lights"
    bl_label = "添加路灯"
    bl_description = "追加团队 Street_Lamp.blend 并沿路布置（Road 2 Light 节点）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        scene = context.scene
        night = getattr(scene, "scg_street_light_night", False)
        if not street_lamp_asset_available():
            self.report({"ERROR"}, "未找到 assets/team/models/lamp/Street_Lamp.blend")
            return {"CANCELLED"}
        ok, message = apply_street_lights(context, night_emission=night)
        if ok:
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


classes = (SCG_OT_apply_street_lights,)
