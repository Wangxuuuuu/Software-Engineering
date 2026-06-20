"""
自然语言 / JSON 命令 handler（阶段四 P0）。

各 handler 签名：(context, params) -> (ok, message)
由 command_executor 按 action 名分发。
"""

from __future__ import annotations

from typing import Any, Callable, Tuple

import bpy

from .city_generator import (
    generate_base_city_from_scene,
    icity_scene_ready,
    set_road_texture,
)
from .dynamic_elements import add_boats, add_cars_and_pedestrians
from .street_lights import apply_street_lights, street_lamp_asset_available
from .template_manager import (
    apply_template,
    set_bench_type,
    set_building_density,
    set_environment,
    set_road_texture_prop,
    set_tree_type,
)

HandlerFn = Callable[[bpy.types.Context, dict[str, Any]], Tuple[bool, str]]


class CommandExecutionError(Exception):
    """命令执行失败，message 供 UI 显示。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _require_icity_ready() -> None:
    if not icity_scene_ready():
        raise CommandExecutionError("请先 Start ICity 并生成基础城市")


def _int_param(params: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError) as exc:
        raise CommandExecutionError(f"参数 {key} 必须是整数") from exc


def _apply_rainy_environment(scene: bpy.types.Scene) -> None:
    """雨天方案 A：夜间环境 + 偏灰世界背景（雨粒子留阶段二）。"""
    set_environment(scene, "night")
    world = scene.world
    if world is None or not world.use_nodes or world.node_tree is None:
        return
    bg = world.node_tree.nodes.get("Background")
    if bg is None:
        return
    bg.inputs[0].default_value = (0.12, 0.14, 0.18, 1.0)
    bg.inputs[1].default_value = 0.35


def handle_apply_template(context: bpy.types.Context, params: dict[str, Any]) -> Tuple[bool, str]:
    _require_icity_ready()
    template_id = str(params.get("template_id", "0"))
    return apply_template(context, template_id)


def handle_apply_asset_config(context: bpy.types.Context, params: dict[str, Any]) -> Tuple[bool, str]:
    _require_icity_ready()
    scene = context.scene

    if "tree_type" in params:
        set_tree_type(scene, _int_param(params, "tree_type", 1))
    if "road_texture" in params:
        set_road_texture_prop(scene, _int_param(params, "road_texture", 1))
    if "bench_type" in params:
        set_bench_type(scene, _int_param(params, "bench_type", 1))
    if "building_density" in params:
        set_building_density(scene, str(params["building_density"]))

    parts = [
        f"树{int(scene.scg_tree_type)}",
        f"路{int(scene.scg_road_type)}",
        f"椅{int(scene.scg_bench_type)}",
    ]

    if params.get("regenerate", True):
        ok, message = generate_base_city_from_scene(scene, context)
        if not ok:
            return False, message
        return True, f"已更新资产配置（{', '.join(parts)}）并重新生成：{message}"

    return True, f"已更新资产配置：{', '.join(parts)}"


def handle_set_road_texture(context: bpy.types.Context, params: dict[str, Any]) -> Tuple[bool, str]:
    _require_icity_ready()
    type_id = _int_param(params, "type", 1)
    if type_id not in (1, 2):
        return False, "道路类型仅支持 1 或 2"
    set_road_texture_prop(context.scene, type_id)
    ok, message = set_road_texture(type_id)
    return ok, message or f"道路纹理已设为类型 {type_id}"


def handle_set_environment(context: bpy.types.Context, params: dict[str, Any]) -> Tuple[bool, str]:
    scene = context.scene
    mode = str(params.get("mode", "day")).lower()

    if mode == "rainy":
        _apply_rainy_environment(scene)
        return True, "已切换雨天模式（环境变暗；雨粒子效果待阶段二扩展）"

    if mode in ("night", "dark", "dusk", "evening"):
        set_environment(scene, "night")
        return True, "已切换夜间环境"

    set_environment(scene, "day")
    return True, "已切换白天环境"


def handle_add_dynamic_element(context: bpy.types.Context, params: dict[str, Any]) -> Tuple[bool, str]:
    _require_icity_ready()
    scene = context.scene
    element_type = str(params.get("type", "car")).lower()
    saved_car = int(getattr(scene, "scg_car_count", 0))
    saved_ped = int(getattr(scene, "scg_pedestrian_count", 0))

    if element_type == "car":
        car_count = _int_param(params, "count", saved_car if saved_car > 0 else 2)
        scene.scg_car_count = max(0, car_count)
        scene.scg_pedestrian_count = 0
        try:
            ok, message = add_cars_and_pedestrians(context)
        finally:
            scene.scg_pedestrian_count = saved_ped
        return ok, message

    if element_type == "boat":
        boat_count = _int_param(params, "count", int(getattr(scene, "scg_boat_count", 1)))
        scene.scg_boat_count = max(0, boat_count)
        return add_boats(context)

    if element_type == "pedestrian":
        ped_count = _int_param(params, "count", saved_ped if saved_ped > 0 else 3)
        scene.scg_car_count = 0
        scene.scg_pedestrian_count = max(0, ped_count)
        try:
            ok, message = add_cars_and_pedestrians(context)
        finally:
            scene.scg_car_count = saved_car
        return ok, message

    return False, f"不支持的动态元素类型: {element_type}"


def handle_add_street_lights(context: bpy.types.Context, params: dict[str, Any]) -> Tuple[bool, str]:
    _require_icity_ready()
    if not street_lamp_asset_available():
        return False, "未找到 assets/team/models/lamp/Street_Lamp.blend"
    night = bool(params.get("night_emission", getattr(context.scene, "scg_street_light_night", False)))
    return apply_street_lights(context, night_emission=night)


NL_COMMAND_HANDLERS: dict[str, HandlerFn] = {
    "apply_template": handle_apply_template,
    "apply_asset_config": handle_apply_asset_config,
    "set_road_texture": handle_set_road_texture,
    "set_environment": handle_set_environment,
    "add_dynamic_element": handle_add_dynamic_element,
    "add_street_lights": handle_add_street_lights,
}
