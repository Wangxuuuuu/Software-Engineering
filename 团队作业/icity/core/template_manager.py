"""
读取 config/templates.json 并一键应用到场景（Day 7-8）。
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional, Tuple

import bpy

from .assets_manager import ADDON_ROOT
from .city_generator import generate_base_city_from_scene

TEMPLATES_PATH = os.path.join(ADDON_ROOT, "config", "templates.json")

_DENSITY_MAP = {
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
}


def load_templates() -> dict[str, Any]:
    if not os.path.isfile(TEMPLATES_PATH):
        return {}
    with open(TEMPLATES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(k): v for k, v in data.items()}


def get_template(template_id: str | int) -> Optional[dict[str, Any]]:
    return load_templates().get(str(template_id))


def template_ids() -> list[str]:
    ids = load_templates().keys()
    return sorted(ids, key=lambda x: int(x) if x.isdigit() else x)


def _type_int_to_scg(value: int) -> str:
    return "1" if int(value) <= 1 else "2"


def format_template_summary(template_id: str, template: Optional[dict[str, Any]] = None) -> str:
    tpl = template or get_template(template_id)
    if not tpl:
        return f"模板 {template_id} 不存在"
    parts = [
        f"树{tpl.get('tree_type', 1)}",
        f"路{tpl.get('road_texture', 1)}",
        f"椅{tpl.get('bench_type', 1)}",
        f"密度{tpl.get('building_density', 'medium')}",
        f"{tpl.get('weather', 'day')}",
    ]
    return "，".join(parts)


def apply_scene_properties_from_template(scene: bpy.types.Scene, template: dict[str, Any]) -> None:
    scene.scg_tree_type = _type_int_to_scg(template.get("tree_type", 1))
    scene.scg_road_type = _type_int_to_scg(template.get("road_texture", 1))
    scene.scg_bench_type = _type_int_to_scg(template.get("bench_type", 1))
    density = str(template.get("building_density", "medium")).lower()
    scene.scg_building_density = _DENSITY_MAP.get(density, "MEDIUM")


def set_environment(scene: bpy.types.Scene, weather: str) -> None:
    """day / night：联动 ICity Light mode 与世界背景（便于 A5 肉眼区分）。"""
    is_night = weather.lower() == "night"

    if hasattr(scene, "sna_light_mode"):
        scene.sna_light_mode = is_night

    try:
        bpy.ops.sna.light_city_20ca9()
    except Exception:
        pass

    world = scene.world
    if world is None or not world.use_nodes or world.node_tree is None:
        return
    bg = world.node_tree.nodes.get("Background")
    if bg is None:
        return
    if is_night:
        bg.inputs[0].default_value = (0.02, 0.03, 0.08, 1.0)
        bg.inputs[1].default_value = 0.25
    else:
        bg.inputs[0].default_value = (0.45, 0.65, 0.95, 1.0)
        bg.inputs[1].default_value = 1.0


def apply_template(
    context: bpy.types.Context,
    template_id: str | int,
) -> Tuple[bool, str]:
    """
    按 templates.json 写入 scg_* → 环境 → 生成基础城市（ICity 默认路灯，不替换团队模型）。
    """
    tpl = get_template(template_id)
    if tpl is None:
        return False, f"未找到模板 {template_id}，请检查 config/templates.json"

    scene = context.scene
    apply_scene_properties_from_template(scene, tpl)
    set_environment(scene, str(tpl.get("weather", "day")))

    ok, message = generate_base_city_from_scene(scene, context)
    if not ok:
        return False, message

    summary = format_template_summary(str(template_id), tpl)
    return True, f"已应用模板 {template_id}：{summary}"


# 兼容主文档命名
def set_tree_type(scene: bpy.types.Scene, type_id: int) -> None:
    scene.scg_tree_type = _type_int_to_scg(type_id)


def set_road_texture_prop(scene: bpy.types.Scene, type_id: int) -> None:
    scene.scg_road_type = _type_int_to_scg(type_id)


def set_bench_type(scene: bpy.types.Scene, type_id: int) -> None:
    scene.scg_bench_type = _type_int_to_scg(type_id)


def set_building_density(scene: bpy.types.Scene, level: str) -> None:
    scene.scg_building_density = _DENSITY_MAP.get(level.lower(), "MEDIUM")
