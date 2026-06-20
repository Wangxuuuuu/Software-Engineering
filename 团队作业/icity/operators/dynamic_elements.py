"""
阶段三 C：车辆 / 行人动态元素 Operator。
"""

from __future__ import annotations

import bpy

from ..core.assets_manager import any_car_model_available, boat_asset_available, people_asset_available
from ..core.city_generator import icity_scene_ready
from ..core.dynamic_elements import add_boats, add_cars_and_pedestrians
from ..core.path_animation import export_manual_paths_to_library
class SCG_OT_adjust_dynamic_count(bpy.types.Operator):
    bl_idname = "scg.adjust_dynamic_count"
    bl_label = "调整数量"
    bl_options = {"INTERNAL"}

    prop_name: bpy.props.StringProperty()
    delta: bpy.props.IntProperty(default=1)

    def execute(self, context):
        scene = context.scene
        if not hasattr(scene, self.prop_name):
            return {"CANCELLED"}
        current = int(getattr(scene, self.prop_name))
        prop = scene.bl_rna.properties.get(self.prop_name)
        minimum = int(getattr(prop, "min", 0)) if prop else 0
        maximum = int(getattr(prop, "max", current + abs(self.delta))) if prop else current + abs(self.delta)
        new_value = max(minimum, min(maximum, current + self.delta))
        setattr(scene, self.prop_name, new_value)
        return {"FINISHED"}


class SCG_OT_add_dynamic_elements(bpy.types.Operator):
    bl_idname = "scg.add_dynamic_elements"
    bl_label = "添加车辆与行人"
    bl_description = "沿 ICity 道路放置车辆与行人，并生成路径动画（无需山水）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        if not any_car_model_available() and not people_asset_available():
            self.report({"ERROR"}, "缺少 cars/source 或 people.blend 资产")
            return {"CANCELLED"}
        ok, message = add_cars_and_pedestrians(context)
        if ok:
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"WARNING"}, message)
        return {"CANCELLED"}


class SCG_OT_export_manual_paths(bpy.types.Operator):
    bl_idname = "scg.export_manual_paths"
    bl_label = "保存曲线到路径库"
    bl_description = (
        "将场景中 SCG_Manual_* 曲线（含 SCG_Manual_Boat）"
        "写入 assets/manual_paths/manual_paths.blend"
    )
    bl_options = {"REGISTER"}

    def execute(self, context):
        ok, message = export_manual_paths_to_library(context)
        if ok:
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"WARNING"}, message)
        return {"CANCELLED"}


class SCG_OT_add_boats(bpy.types.Operator):
    bl_idname = "scg.add_boats"
    bl_label = "添加船只"
    bl_description = "在湖面环绕放置船只动画（需先添加中央山水）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        if not boat_asset_available():
            self.report({"ERROR"}, f"缺少船只资产")
            return {"CANCELLED"}
        ok, message = add_boats(context)
        if ok:
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"WARNING"}, message)
        return {"CANCELLED"}


classes = (
    SCG_OT_adjust_dynamic_count,
    SCG_OT_add_dynamic_elements,
    SCG_OT_export_manual_paths,
    SCG_OT_add_boats,
)
