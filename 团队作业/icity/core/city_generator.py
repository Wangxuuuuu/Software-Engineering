"""
封装 ICity 场景操作：一键生成基础城市（Day 2-3）。
"""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple

import bpy

from .assets_manager import (
    ADDON_ROOT,
    icity_road_material_name,
    road_texture_available,
    road_texture_label,
    road_texture_paths,
)

ICITY_START_BLEND = os.path.join(ADDON_ROOT, "assets", "ICity start.blend")

DENSITY_FLOOR_RANGE = {
    "LOW": (2, 5),
    "MEDIUM": (4, 10),
    "HIGH": (8, 18),
}

_ICITY_REFRESH_OBJECTS = (
    "ICity Base",
    "ICity Road",
    "ICity Spces",
    "ICity Procedural ground",
    "ICity building procedural base",
)


def icity_collection_exists() -> bool:
    return bpy.data.collections.get("ICity") is not None


def icity_base_exists() -> bool:
    return bpy.data.objects.get("ICity Base") is not None


def icity_scene_ready() -> bool:
    return icity_collection_exists() and icity_base_exists()


def ensure_icity_started() -> bool:
    if not icity_collection_exists():
        bpy.ops.sna.start_5209e("EXEC_DEFAULT")
    return icity_base_exists()


def _type_enum_to_index(prop_value: str) -> int:
    try:
        return max(0, int(prop_value) - 1)
    except (TypeError, ValueError):
        return 0


def _ensure_object_mode_icity_base(context: bpy.types.Context) -> Optional[bpy.types.Object]:
    """
    在 Object 模式下写 Attribute，避免 Edit 模式下 BMesh 缓存导致几何节点不刷新。
    """
    obj = bpy.data.objects.get("ICity Base")
    if obj is None:
        return None
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def enter_icity_edit_mode(context: bpy.types.Context) -> bool:
    """仅进入 Edit City，不切换退出（区别于 sna.edit_city_d7cab 的 toggle）。"""
    obj = bpy.data.objects.get("ICity Base")
    if obj is None:
        return False
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    if context.mode != "EDIT_MESH":
        bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.sna.light_city_20ca9()
    except Exception:
        pass
    return True


def _fill_attribute(mesh: bpy.types.Mesh, name: str, value: Any) -> bool:
    attr = mesh.attributes.get(name)
    if attr is None:
        return False
    dtype = attr.data_type
    for item in attr.data:
        if dtype == "INT":
            item.value = int(value)
        elif dtype == "FLOAT":
            item.value = float(value)
        elif dtype == "BOOLEAN":
            item.value = bool(value)
        else:
            return False
    return True


def _object_from_collection(collection_name: str, type_index: int) -> Optional[bpy.types.Object]:
    coll = bpy.data.collections.get(collection_name)
    if coll is None or len(coll.objects) == 0:
        return None
    idx = min(max(0, type_index), len(coll.objects) - 1)
    return coll.objects[idx]


def _apply_road_node_object(street_type: str, obj: Optional[bpy.types.Object]) -> None:
    if obj is None:
        return
    ng = bpy.data.node_groups.get("Road 2")
    if ng is None or street_type not in ng.nodes:
        return
    try:
        ng.nodes[street_type].inputs[4].default_value = obj
    except (KeyError, TypeError, AttributeError):
        pass


def _load_image(path: str) -> Optional[bpy.types.Image]:
    import os

    if not path or not os.path.isfile(path):
        return None
    try:
        return bpy.data.images.load(path, check_existing=True)
    except RuntimeError:
        return None


def _add_image_tex(
    nodes: bpy.types.Nodes,
    links: bpy.types.NodeLinks,
    bsdf: bpy.types.Node,
    path: str | None,
    *,
    socket: str,
    non_color: bool = False,
) -> None:
    img = _load_image(path)
    if img is None:
        return
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    if non_color:
        tex.image.colorspace_settings.name = "Non-Color"
    links.new(tex.outputs["Color"], bsdf.inputs[socket])


def _append_icity_road_material(material_name: str) -> Optional[bpy.types.Material]:
    """从 ICity Materials.blend 追加官方道路材质（与原生 Road→Texture 一致）。"""
    import os

    if not os.path.isfile(ICITY_MATERIALS_BLEND):
        return None
    existing = bpy.data.materials.get(material_name)
    if existing:
        return existing
    before = set(bpy.data.materials)
    try:
        bpy.ops.wm.append(
            filepath=os.path.join(ICITY_MATERIALS_BLEND, "Material", material_name),
            directory=os.path.join(ICITY_MATERIALS_BLEND, "Material"),
            filename=material_name,
            link=False,
        )
    except RuntimeError:
        return None
    new_mats = [m for m in bpy.data.materials if m not in before]
    return new_mats[0] if new_mats else bpy.data.materials.get(material_name)


def _build_road_material(type_id: int) -> Optional[bpy.types.Material]:
    """
    完整 PBR 道路材质。必须有 BaseColor（color）才能在视口看到路面纹理；
    Normal / Roughness / Height 为附加细节。
    """
    paths = road_texture_paths(type_id)
    color_path = paths.get("color")

    if color_path and _load_image(color_path) is None:
        # BaseColor 缺失时尝试 ICity 官方材质
        icity_name = icity_road_material_name(type_id)
        if icity_name:
            return _append_icity_road_material(icity_name)
        return None

    if not road_texture_available(type_id):
        return None

    mat_name = f"SCG_Road_Type{type_id}"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.7

    _add_image_tex(nodes, links, bsdf, paths.get("color"), socket="Base Color")
    _add_image_tex(nodes, links, bsdf, paths.get("normal"), socket="Normal", non_color=True)
    _add_image_tex(nodes, links, bsdf, paths.get("roughness"), socket="Roughness", non_color=True)

    height_path = paths.get("height")
    img_h = _load_image(height_path) if height_path else None
    if img_h:
        tex_h = nodes.new("ShaderNodeTexImage")
        tex_h.image = img_h
        tex_h.image.colorspace_settings.name = "Non-Color"
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.4
        links.new(tex_h.outputs["Color"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def set_road_texture(type_id: int) -> Tuple[bool, str]:
    """
    创建/更新道路材质并写入 Road 2 节点组（阶段二 Day 5-6）。
    type_id: 1 或 2，与 scg_road_type / templates.json 一致。
    """
    if type_id not in (1, 2):
        type_id = 1

    ng = bpy.data.node_groups.get("Road 2")
    if ng is None or "Road" not in ng.nodes:
        return False, "未找到 Road 2 节点组，请先 Start"

    if not road_texture_available(type_id):
        return False, f"类型{type_id} 贴图文件不存在，请检查 assets/team/textures/"

    mat = _build_road_material(type_id)
    if mat is None:
        return False, f"无法构建道路材质（类型{type_id}）"

    try:
        ng.nodes["Road"].inputs[2].default_value = mat
    except (KeyError, TypeError, AttributeError):
        return False, "无法写入 Road 2.nodes['Road'].inputs[2]"

    road_obj = bpy.data.objects.get("ICity Road")
    if road_obj:
        road_obj.update_tag(refresh={"DATA"})

    _flush_viewport_refresh()

    return True, (
        f"已应用道路纹理：{road_texture_label(type_id)}"
        "（请使用视口「材质预览」或「渲染」查看）"
    )


def _apply_road_texture(road_type_index: int) -> None:
    """生成基础城市时调用；road_type_index 为 0-based。"""
    set_road_texture(road_type_index + 1)


def _refresh_procedural_buildings() -> None:
    if not bpy.data.collections.get("ICity_Procedural"):
        return
    try:
        bpy.ops.sna.procedural_building_filter_05bed()
    except Exception:
        pass
    try:
        bpy.ops.sna.park_filter_5a7a2()
    except Exception:
        pass
    try:
        bpy.ops.sna.sync_city_76707()
    except Exception:
        pass


def _flush_viewport_refresh() -> None:
    """强制几何节点与视口更新。"""
    for name in _ICITY_REFRESH_OBJECTS:
        obj = bpy.data.objects.get(name)
        if obj:
            if obj.data:
                obj.data.update()
            obj.update_tag(refresh={"DATA"})
    coll = bpy.data.collections.get("ICity_Procedural")
    if coll:
        for obj in coll.all_objects:
            obj.update_tag(refresh={"DATA"})
    view_layer = bpy.context.view_layer
    if view_layer:
        view_layer.update()
    try:
        bpy.context.evaluated_depsgraph_get().update()
    except Exception:
        pass
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


def _sync_icity_scene_props_for_ui(scene: bpy.types.Scene, building_index: int) -> None:
    if hasattr(scene, "sna_city_space_type"):
        scene.sna_city_space_type = "Procedural"
    coll = bpy.data.collections.get("ICity_Procedural")
    if coll and coll.all_objects and hasattr(scene, "sna_procedural_building_browser"):
        names = [o.name for o in coll.all_objects]
        idx = min(building_index, len(names) - 1)
        scene.sna_procedural_building_browser = names[idx]


def apply_mesh_city_attributes(
    mesh: bpy.types.Mesh,
    *,
    city_scale: str,
    building_density: str,
    procedural_index: int,
    park_index: int = 0,
) -> None:
    floor_min, floor_max = DENSITY_FLOOR_RANGE.get(building_density, (4, 10))
    attr_space = mesh.attributes.get("space type")
    if attr_space is None:
        return

    n_faces = len(attr_space.data)
    half = n_faces // 2 if n_faces else 0

    if city_scale == "SMALL":
        for i, item in enumerate(attr_space.data):
            item.value = 0 if i < half else 1
        attr_proc = mesh.attributes.get("Procedural index")
        if attr_proc:
            for i, item in enumerate(attr_proc.data):
                item.value = procedural_index if i < half else 0
        attr_park = mesh.attributes.get("Park")
        if attr_park:
            for i, item in enumerate(attr_park.data):
                item.value = park_index if i >= half else 0
    else:
        _fill_attribute(mesh, "space type", 0)
        _fill_attribute(mesh, "Procedural index", procedural_index)

    _fill_attribute(mesh, "Floor count", floor_min)
    _fill_attribute(mesh, "Floor count max", floor_max)


def apply_mesh_road_attributes(mesh: bpy.types.Mesh) -> None:
    _fill_attribute(mesh, "Road del", False)
    for attr_name, val in (
        ("Light", False),
        ("Tree", True),
        ("Bench", True),
    ):
        if mesh.attributes.get(attr_name) is not None:
            _fill_attribute(mesh, attr_name, val)


def generate_base_city_from_scene(
    scene: bpy.types.Scene,
    context: Optional[bpy.types.Context] = None,
) -> Tuple[bool, str]:
    if context is None:
        context = bpy.context

    if not ensure_icity_started():
        return False, "Start 失败：未找到 ICity Base"

    obj = _ensure_object_mode_icity_base(context)
    if obj is None:
        return False, "未找到 ICity Base"

    building_idx = _type_enum_to_index(scene.scg_building_type)
    road_idx = _type_enum_to_index(scene.scg_road_type)
    tree_idx = _type_enum_to_index(scene.scg_tree_type)
    bench_idx = _type_enum_to_index(scene.scg_bench_type)

    mesh = obj.data

    apply_mesh_city_attributes(
        mesh,
        city_scale=scene.scg_city_scale,
        building_density=scene.scg_building_density,
        procedural_index=building_idx,
        park_index=0,
    )
    apply_mesh_road_attributes(mesh)

    _apply_road_texture(road_idx)
    _apply_road_node_object("Light", _object_from_collection("ICity_Light", 0))
    _apply_road_node_object("Tree", _object_from_collection("ICity_Tree", tree_idx))
    _apply_road_node_object("Bench", _object_from_collection("ICity_Bench", bench_idx))

    _sync_icity_scene_props_for_ui(scene, building_idx)

    mesh.update()
    _flush_viewport_refresh()
    _refresh_procedural_buildings()
    _flush_viewport_refresh()

    scale_label = "小型" if scene.scg_city_scale == "SMALL" else "中型"
    return True, (
        f"已生成基础城市：规模={scale_label}，密度={scene.scg_building_density}，"
        f"建筑/道路/树/椅=类型{building_idx + 1}/{road_idx + 1}/"
        f"{tree_idx + 1}/{bench_idx + 1}。（Object 模式已刷新）"
    )


def restore_icity_base_mesh(context: bpy.types.Context) -> Tuple[bool, str]:
    """
    从 ICity start.blend 复制默认 ICity Base 网格，替换自定义布局后的简化拓扑。
    """
    if not os.path.isfile(ICITY_START_BLEND):
        return False, f"未找到 {ICITY_START_BLEND}，请重新 Start ICity"

    target = bpy.data.objects.get("ICity Base")
    if target is None:
        return False, "未找到 ICity Base"

    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    before_objs = set(bpy.data.objects)
    try:
        with bpy.data.libraries.load(ICITY_START_BLEND, link=False) as (data_from, data_to):
            if "ICity Base" not in data_from.objects:
                return False, "start.blend 内无 ICity Base 对象"
            data_to.objects = ["ICity Base"]
    except OSError as exc:
        return False, f"读取 start.blend 失败：{exc}"

    new_objs = [o for o in bpy.data.objects if o not in before_objs]
    template_obj = next((o for o in new_objs if o.type == "MESH"), None)
    if template_obj is None:
        return False, "无法从 start.blend 加载 ICity Base 模板"

    old_mesh = target.data
    restored_mesh = template_obj.data.copy()
    restored_mesh.name = "ICity Base"
    target.data = restored_mesh

    template_mesh = template_obj.data
    bpy.data.objects.remove(template_obj, do_unlink=True)
    if template_mesh.users == 0:
        bpy.data.meshes.remove(template_mesh)
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

    for o in context.view_layer.objects:
        o.select_set(False)
    target.select_set(True)
    context.view_layer.objects.active = target
    target.data.update()
    _flush_viewport_refresh()

    vert_count = len(target.data.vertices)
    return True, f"已还原 ICity Base 默认道路网格（{vert_count} 顶点）"


def restore_base_city_from_scene(
    scene: bpy.types.Scene,
    context: Optional[bpy.types.Context] = None,
) -> Tuple[bool, str]:
    """还原默认 Base 拓扑 + 按面板参数重新「生成基础城市」。"""
    if context is None:
        context = bpy.context

    ok, restore_msg = restore_icity_base_mesh(context)
    if not ok:
        return False, restore_msg

    ok_gen, gen_msg = generate_base_city_from_scene(scene, context)
    if not ok_gen:
        return False, f"{restore_msg}；重新生成失败：{gen_msg}"

    return True, f"{restore_msg}；{gen_msg}"
