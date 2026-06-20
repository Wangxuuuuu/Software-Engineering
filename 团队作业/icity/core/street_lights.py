"""
团队路灯 3D 资产：append + 写入 ICity Road 2 Light 节点（Day 6-7）。
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import bmesh
import bpy

from .assets_manager import (
    SCG_STREET_LAMP_OBJECT_NAME,
    STREET_LAMP_OBJECT_NAME,
    STREET_LAMP_TEXTURE_SEARCH_DIRS,
    STREET_LIGHT_BLEND,
    street_lamp_asset_available,
)
from .city_generator import (
    _apply_road_node_object,
    _flush_viewport_refresh,
    icity_scene_ready,
)


def _move_object_to_collection(obj: bpy.types.Object, collection_name: str) -> None:
    coll = bpy.data.collections.get(collection_name)
    if coll is None:
        return
    for user_coll in list(obj.users_collection):
        user_coll.objects.unlink(obj)
    coll.objects.link(obj)


def _icity_light_reference_size() -> float:
    """参考 Start 后 ICity_Light 集合内官方路灯的大致尺寸（米级）。"""
    coll = bpy.data.collections.get("ICity_Light")
    if coll:
        for obj in coll.objects:
            if obj.name == SCG_STREET_LAMP_OBJECT_NAME or obj.type != "MESH":
                continue
            return max(obj.dimensions.x, obj.dimensions.y, obj.dimensions.z)
    return 3.0


def _normalize_lamp_for_icity(obj: bpy.types.Object, context: bpy.types.Context) -> None:
    """
    修正团队模型常见的问题：尺度过大、躺平（轴向与 ICity 实例化不一致）。
    ICity 沿路实例化时期望「灯柱沿竖直方向」的模板 Object。
    """
    ref = _icity_light_reference_size()

    # 若模型在 XY 上很「扁长」、Z 很矮，视为躺平 → 绕 X 轴扶起
    dx, dy, dz = obj.dimensions.x, obj.dimensions.y, obj.dimensions.z
    if dz < max(dx, dy) * 0.45:
        obj.rotation_euler[0] = 1.57079632679

    max_dim = max(obj.dimensions.x, obj.dimensions.y, obj.dimensions.z)
    if max_dim > ref * 2.5:
        s = ref / max_dim
        obj.scale = (obj.scale.x * s, obj.scale.y * s, obj.scale.z * s)

    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = {o for o in view_layer.objects if o.select_get()}
    try:
        for o in view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    finally:
        for o in view_layer.objects:
            o.select_set(o in prev_selected)
        if prev_active:
            view_layer.objects.active = prev_active


def _iter_lamp_materials(obj: bpy.types.Object):
    mats = {slot.material for slot in obj.material_slots if slot.material}
    for child in obj.children:
        mats.update(slot.material for slot in child.material_slots if slot.material)
    return mats


def _relink_lamp_textures(obj: bpy.types.Object) -> int:
    """
    append 后材质里的 Image 常仍指向旧绝对路径 → 视口粉紫色。
    按文件名在 assets/team/models/lamp/Textures 与 lamp/ 下重新加载。
    """
    fixed = 0
    for mat in _iter_lamp_materials(obj):
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            img = node.image
            if img.filepath:
                try:
                    if os.path.isfile(bpy.path.abspath(img.filepath)):
                        continue
                except ValueError:
                    pass

            names: list[str] = []
            if img.filepath:
                names.append(os.path.basename(bpy.path.abspath(img.filepath)))
            names.append(img.name)
            if "." not in img.name:
                names.append(f"{img.name}.png")

            resolved: str | None = None
            for base in names:
                if not base:
                    continue
                for search_dir in STREET_LAMP_TEXTURE_SEARCH_DIRS:
                    candidate = os.path.join(search_dir, base)
                    if os.path.isfile(candidate):
                        resolved = candidate
                        break
                if resolved:
                    break

            if resolved:
                node.image = bpy.data.images.load(resolved, check_existing=True)
                fixed += 1

    return fixed


def _enable_light_on_street_edges(mesh: bpy.types.Mesh) -> int:
    """
    仅对「道路边、且非中心放射辐条」写入 Light=True。

    ICity Base 网格常含从中心连向边界的辐条边；若对全部边开 Light，
    路灯会沿辐条铺满整个平面（用户看到的放射状错误）。
    """
    attr_light = mesh.attributes.get("Light")
    if attr_light is None:
        return 0

    attr_road = mesh.attributes.get("Road del")

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    hub = max(bm.verts, key=lambda v: len(v.link_edges))

    enabled = 0
    for idx, item in enumerate(attr_light.data):
        if idx >= len(bm.edges):
            item.value = False
            continue
        edge = bm.edges[idx]

        is_road = True
        if attr_road is not None and idx < len(attr_road.data):
            is_road = not attr_road.data[idx].value

        if not is_road or hub in edge.verts:
            item.value = False
            continue

        item.value = True
        enabled += 1

    bm.free()
    return enabled


def _append_street_lamp_from_blend(context: bpy.types.Context) -> Optional[bpy.types.Object]:
    if not street_lamp_asset_available():
        return None

    existing = bpy.data.objects.get(SCG_STREET_LAMP_OBJECT_NAME)
    if existing:
        _normalize_lamp_for_icity(existing, context)
        _relink_lamp_textures(existing)
        return existing

    object_name = STREET_LAMP_OBJECT_NAME
    before = set(bpy.data.objects)

    try:
        bpy.ops.wm.append(
            filepath=os.path.join(STREET_LIGHT_BLEND, "Object", object_name),
            directory=os.path.join(STREET_LIGHT_BLEND, "Object"),
            filename=object_name,
            link=False,
        )
    except RuntimeError:
        return None

    new_objects = [o for o in bpy.data.objects if o not in before]
    obj = new_objects[0] if new_objects else bpy.data.objects.get(object_name)
    if obj is None:
        return None

    if obj.name != SCG_STREET_LAMP_OBJECT_NAME:
        obj.name = SCG_STREET_LAMP_OBJECT_NAME

    _normalize_lamp_for_icity(obj, context)
    _relink_lamp_textures(obj)
    _move_object_to_collection(obj, "ICity_Light")
    return obj


def _set_lamp_emission(obj: bpy.types.Object, enabled: bool) -> None:
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        if enabled:
            bsdf.inputs["Emission Strength"].default_value = 3.0
            base = bsdf.inputs["Base Color"].default_value
            bsdf.inputs["Emission Color"].default_value = (base[0], base[1], base[2], 1.0)
        else:
            bsdf.inputs["Emission Strength"].default_value = 0.0


def apply_street_lights(
    context: bpy.types.Context,
    *,
    night_emission: bool = False,
) -> Tuple[bool, str]:
    if not icity_scene_ready():
        return False, "请先 Start 并确保存在 ICity Base"

    if not street_lamp_asset_available():
        return False, f"未找到 {STREET_LIGHT_BLEND}"

    lamp_obj = _append_street_lamp_from_blend(context)
    if lamp_obj is None:
        return False, f"无法从 blend 追加 Object「{STREET_LAMP_OBJECT_NAME}」"

    base_obj = bpy.data.objects.get("ICity Base")
    edge_count = 0
    if base_obj and base_obj.data:
        edge_count = _enable_light_on_street_edges(base_obj.data)
        base_obj.data.update()

    _apply_road_node_object("Light", lamp_obj)
    _set_lamp_emission(lamp_obj, night_emission)
    _flush_viewport_refresh()

    mode = "（夜间 Emission 开）" if night_emission else "（日间）"
    return True, (
        f"已应用团队路灯：{SCG_STREET_LAMP_OBJECT_NAME} {mode}；"
        f"已启用 {edge_count} 条路边（不含中心放射边）"
    )


def add_street_lights(
    context: bpy.types.Context,
    count: int = 0,
    spacing: float = 0.0,
) -> Tuple[bool, str]:
    _ = count, spacing
    return apply_street_lights(context, night_emission=False)
