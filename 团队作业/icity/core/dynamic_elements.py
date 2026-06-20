"""
动态元素：车辆 / 行人 / 船只路径动画（阶段三 C）。
"""

from __future__ import annotations

import math
import os
import re
from typing import Iterable, Optional, Tuple

import bpy
from mathutils import Vector

from .assets_manager import (
    BOAT_BLEND,
    BOAT_OBJECT_NAME,
    PEOPLE_BLEND,
    boat_asset_available,
    car_blend_path,
    car_model_available,
    car_texture_search_dirs,
    people_asset_available,
    people_texture_search_dirs,
)
from .city_generator import _flush_viewport_refresh, icity_scene_ready
from .path_animation import (
    MANUAL_PATH_BOAT,
    MANUAL_PATH_CAR_CCW,
    MANUAL_PATH_CAR_CW,
    MANUAL_PATH_PED_INNER,
    MANUAL_PATH_PED_OUTER,
    add_follow_path_animation,
    cleanup_path_objects,
    create_boat_water_loop_curve,
    create_lane_loop_curve,
    SCG_PATH_BOAT_LOOP,
    SCG_PATH_COLLECTION,
    SCG_PATH_PREFIX,
    create_sidewalk_loop_curve,
    create_pedestrian_paths_from_lane_curves,
    distributed_boat_path_offsets,
    ensure_manual_boat_path_in_scene,
    ensure_manual_car_paths_in_scene,
    extract_street_loop,
    find_manual_path,
    get_animation_frame_range,
    get_road_cross_section,
    link_path_to_collection,
    prepare_manual_boat_path_for_animation,
    prepare_path_curve_for_animation,
    random_spaced_path_offsets,
    _loop_center,
)
from .scene_enhance import get_road_surface_z, get_water_surface_z, landscape_surround_exists

SCG_DYNAMICS_COLLECTION = "SCG_Dynamics"
SCG_CAR_PREFIX = "SCG_Car_"
SCG_PED_PREFIX = "SCG_Ped_"
SCG_BOAT_PREFIX = "SCG_Boat_"

_CAR_FORWARD_AXIS = "TRACK_NEGATIVE_Y"
_PED_FORWARD_AXIS = "TRACK_NEGATIVE_Y"
# 车辆/船只 root 动画：本地 +Y 为船头/车头
_CAR_FORWARD_LOCAL = Vector((0.0, 1.0, 0.0))
# 船只船头：相对当前朝向再转 180°（本地 -Y 朝前）
_BOAT_FORWARD_LOCAL = Vector((0.0, -1.0, 0.0))
_PED_FORWARD_LOCAL = Vector((0.0, -1.0, 0.0))
# 里圈人行道切线方向与外圈相反，正面轴需翻转 180°
_PED_INNER_FORWARD_LOCAL = Vector((0.0, 1.0, 0.0))
_CAR_MESH_YAW_CORRECTION = 0.0
_BOAT_MESH_YAW_CORRECTION = math.pi
_PED_MESH_YAW_CORRECTION = math.pi
_PED_NATIVE_HEIGHT = 9.41
_PED_TARGET_HEIGHT = 1.75
_BOAT_TARGET_LENGTH_M = 7.0
_BOAT_WATERLINE_RATIO = 0.42

_CAR_LOOP_PROGRESS = 0.38
_PED_SPEED_RATIO = 1.0 / 6.0
_BOAT_SPEED_RATIO = _PED_SPEED_RATIO * 0.25
_MANUAL_BOAT_LOOP_PROGRESS = 0.09
_PEOPLE_LIB_LOADED = False


def _ensure_collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _move_to_collection(objects: Iterable[bpy.types.Object], collection_name: str) -> None:
    coll = _ensure_collection(collection_name)
    coll.hide_viewport = False
    coll.hide_render = False
    for obj in objects:
        for user_coll in list(obj.users_collection):
            user_coll.objects.unlink(obj)
        coll.objects.link(obj)


def _move_rig_to_collection(
    root: bpy.types.Object,
    parts: list[bpy.types.Object],
    collection_name: str,
) -> None:
    """将 rig 根节点与子 mesh 挂到同一集合层级，避免取消选中后子级不可见。"""
    coll = _ensure_collection(collection_name)
    coll.hide_viewport = False
    coll.hide_render = False

    bpy.context.view_layer.update()
    for part in parts:
        if part.parent != root:
            world = part.matrix_world.copy()
            part.parent = root
            part.matrix_world = world

    root.hide_viewport = False
    for part in parts:
        part.hide_viewport = False

    for obj in (root, *parts):
        for user_coll in list(obj.users_collection):
            user_coll.objects.unlink(obj)

    coll.objects.link(root)
    for part in parts:
        try:
            coll.objects.link(part, parent=root)
        except TypeError:
            coll.objects.link(part)


def _ensure_object_mode(context: bpy.types.Context) -> None:
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _car_ped_objects() -> list[bpy.types.Object]:
    return [
        obj for obj in bpy.data.objects
        if obj.name.startswith(SCG_CAR_PREFIX) or obj.name.startswith(SCG_PED_PREFIX)
    ]


def _boat_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.data.objects if obj.name.startswith(SCG_BOAT_PREFIX)]


def _dynamic_root_objects() -> list[bpy.types.Object]:
    return _car_ped_objects() + _boat_objects()


def _dynamics_exists() -> bool:
    return len(_dynamic_root_objects()) > 0


def cleanup_cars_and_pedestrians() -> None:
    """仅移除车辆、行人与道路路径（保留船只）。"""
    for obj in _car_ped_objects():
        bpy.data.objects.remove(obj, do_unlink=True)
    for obj in list(bpy.data.objects):
        if not obj.name.startswith(SCG_PATH_PREFIX):
            continue
        if obj.name == SCG_PATH_BOAT_LOOP:
            continue
        bpy.data.objects.remove(obj, do_unlink=True)


def cleanup_boats() -> None:
    """仅移除船只与湖面路径。"""
    for obj in _boat_objects():
        bpy.data.objects.remove(obj, do_unlink=True)
    boat_path = bpy.data.objects.get(SCG_PATH_BOAT_LOOP)
    if boat_path is not None:
        bpy.data.objects.remove(boat_path, do_unlink=True)


def cleanup_dynamic_elements(context: Optional[bpy.types.Context] = None) -> None:
    """移除 SCG 车辆、行人、船只与全部路径。"""
    _ = context
    cleanup_cars_and_pedestrians()
    cleanup_boats()

    coll = bpy.data.collections.get(SCG_PATH_COLLECTION)
    if coll is not None and len(coll.all_objects) == 0:
        bpy.data.collections.remove(coll)

    dyn_coll = bpy.data.collections.get(SCG_DYNAMICS_COLLECTION)
    if dyn_coll is not None and len(dyn_coll.all_objects) == 0:
        bpy.data.collections.remove(dyn_coll)


def _image_feeds_normal_map(mat: bpy.types.Material, image_node: bpy.types.Node) -> bool:
    if not mat.use_nodes:
        return False
    for link in mat.node_tree.links:
        if (
            link.from_node == image_node
            and link.to_node.type == "NORMAL_MAP"
            and link.to_socket.name == "Color"
        ):
            return True
    return False


def _iter_material_images(obj: bpy.types.Object):
    mats = {slot.material for slot in obj.material_slots if slot.material}
    for child in obj.children:
        mats.update(slot.material for slot in child.material_slots if slot.material)
    for mat in mats:
        if mat is None or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                yield mat, node


def _strip_blender_image_suffix(name: str) -> str:
    """orange.jpg.001 → orange.jpg"""
    match = re.match(r"^(.*\.(?:jpg|jpeg|png|bmp|tga|exr|tif|tiff))(?:\.\d+)?$", name, re.I)
    if match:
        return match.group(1)
    match = re.match(r"^(.*)\.\d+$", name)
    if match:
        return match.group(1)
    return name


def _image_is_valid(img: bpy.types.Image) -> bool:
    if img.packed_file is not None:
        return True
    if img.size[0] > 0 and img.size[1] > 0:
        return True
    if img.filepath:
        try:
            return os.path.isfile(bpy.path.abspath(img.filepath))
        except ValueError:
            pass
    return False


def _texture_lookup_names(img: bpy.types.Image) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        name = name.strip()
        if not name or name in seen:
            return
        seen.add(name)
        names.append(name)

    if img.filepath:
        try:
            _add(os.path.basename(bpy.path.abspath(img.filepath)))
        except ValueError:
            _add(os.path.basename(img.filepath.replace("\\", "/")))
        rel = img.filepath.replace("\\", "/")
        if rel.startswith("//"):
            _add(os.path.basename(rel[2:]))
    _add(img.name)
    stripped = _strip_blender_image_suffix(img.name)
    _add(stripped)
    if "." not in stripped:
        for ext in (".png", ".jpg", ".jpeg", ".bmp"):
            _add(stripped + ext)
    return names


def _resolve_texture_file(names: list[str], search_dirs: tuple[str, ...]) -> str | None:
    for base in names:
        if not base:
            continue
        for search_dir in search_dirs:
            candidate = os.path.join(search_dir, base)
            if os.path.isfile(candidate):
                return candidate
    return None


def _get_solid_image(key: str, rgba: tuple[float, float, float, float], size: int = 4) -> bpy.types.Image:
    safe_key = re.sub(r"[^\w\-]+", "_", key)[:80]
    name = f"SCG_SolidTex_{safe_key}"
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.new(name, width=size, height=size, alpha=True)
    pixels = list(rgba) * (size * size)
    img.pixels.foreach_set(pixels)
    return img


def _fallback_rgba_for_texture(
    mat_name: str,
    img_name: str,
    node_label: str,
) -> tuple[float, float, float, float]:
    combined = f"{mat_name} {img_name} {node_label}".lower()
    if "normal" in combined or "nor_gl" in combined:
        return (0.5, 0.5, 1.0, 1.0)
    if "roughness" in combined or "rough" in combined:
        return (0.35, 0.35, 0.35, 1.0)
    if "metalness" in combined or "metallic" in combined:
        return (0.85, 0.85, 0.85, 1.0)
    if "tyre" in combined or "tire" in combined:
        return (0.06, 0.06, 0.06, 1.0)
    if "rim" in combined or "wheel" in mat_name.lower():
        return (0.55, 0.56, 0.58, 1.0)
    if "black" in combined:
        return (0.03, 0.03, 0.03, 1.0)
    if "orange" in combined or mat_name.lower() == "body":
        return (0.82, 0.28, 0.08, 1.0)
    if "screen" in combined:
        return (0.05, 0.08, 0.12, 1.0)
    if "grill" in combined or "speaker" in combined:
        return (0.12, 0.12, 0.12, 1.0)
    if "gold" in combined:
        return (0.72, 0.58, 0.15, 1.0)
    if "glass" in mat_name.lower():
        return (0.75, 0.82, 0.88, 0.25)
    if mat_name.lower() in {"light", "lights"}:
        return (1.0, 0.95, 0.85, 1.0)
    if "red light" in mat_name.lower():
        return (0.9, 0.08, 0.05, 1.0)
    return (0.45, 0.45, 0.48, 1.0)


def _relink_textures_in_objects(
    objects: Iterable[bpy.types.Object],
    search_dirs: tuple[str, ...],
) -> int:
    fixed = 0
    for obj in objects:
        for _mat, node in _iter_material_images(obj):
            img = node.image
            if _image_is_valid(img):
                continue
            resolved = _resolve_texture_file(_texture_lookup_names(img), search_dirs)
            if resolved:
                node.image = bpy.data.images.load(resolved, check_existing=True)
                fixed += 1
    return fixed


def _apply_car_texture_fallbacks(objects: Iterable[bpy.types.Object]) -> int:
    """缺失外部贴图时用纯色块替代，避免材质预览粉紫色。"""
    fixed = 0
    for obj in objects:
        for mat, node in _iter_material_images(obj):
            img = node.image
            if img is None or _image_is_valid(img):
                continue
            rgba = _fallback_rgba_for_texture(mat.name, img.name, node.label or "")
            node.image = _get_solid_image(f"{mat.name}_{img.name}", rgba)
            fixed += 1
    return fixed


def _fallback_rgba_for_people_texture(
    mat_name: str,
    img_name: str,
    node_label: str,
) -> tuple[float, float, float, float]:
    combined = f"{mat_name} {img_name} {node_label}".lower()
    if "normal" in combined or "nor_gl" in combined:
        return (0.5, 0.5, 1.0, 1.0)
    if "roughness" in combined or "rough" in combined:
        return (0.45, 0.45, 0.45, 1.0)
    if "metalness" in combined or "metallic" in combined:
        return (0.05, 0.05, 0.05, 1.0)
    if "skin" in combined or "face" in combined or "body" in combined:
        return (0.76, 0.60, 0.50, 1.0)
    if "hair" in combined:
        return (0.18, 0.14, 0.10, 1.0)
    if any(k in combined for k in ("shirt", "cloth", "top", "jacket", "coat")):
        return (0.32, 0.42, 0.62, 1.0)
    if any(k in combined for k in ("pants", "trouser", "jean", "skirt", "short")):
        return (0.22, 0.24, 0.30, 1.0)
    if "shoe" in combined or "boot" in combined:
        return (0.12, 0.12, 0.12, 1.0)
    return (0.52, 0.52, 0.55, 1.0)


def _apply_people_texture_fallbacks(objects: Iterable[bpy.types.Object]) -> int:
    """行人缺失贴图时用肤色/衣物色替代，避免误用车辆橙色 body。"""
    fixed = 0
    for obj in objects:
        for mat, node in _iter_material_images(obj):
            img = node.image
            if img is None or _image_is_valid(img):
                continue
            if _image_feeds_normal_map(mat, node):
                rgba = (0.5, 0.5, 1.0, 1.0)
            else:
                rgba = _fallback_rgba_for_people_texture(mat.name, img.name, node.label or "")
            node.image = _get_solid_image(f"SCG_Ped_{mat.name}_{img.name}", rgba)
            fixed += 1
    return fixed


def _ensure_people_blend_library() -> bool:
    """一次性加载 people.blend 的材质/贴图，避免重复 append 导致贴图 .001 错位与橘色描边。"""
    global _PEOPLE_LIB_LOADED
    if _PEOPLE_LIB_LOADED:
        return True
    if not os.path.isfile(PEOPLE_BLEND):
        return False
    try:
        with bpy.data.libraries.load(PEOPLE_BLEND, link=False) as (data_from, data_to):
            data_to.materials = list(data_from.materials)
            data_to.images = list(data_from.images)
    except OSError:
        return False
    _PEOPLE_LIB_LOADED = True
    return True


def _append_car_blend_objects(blend_path: str) -> list[bpy.types.Object]:
    """Append 车辆：同时加载 objects / materials / images，保留已打包贴图。"""
    if not os.path.isfile(blend_path):
        return []
    skip_names = {"camera", "cube", "light", "plane"}
    skip_types = {"CAMERA", "LIGHT"}
    before = set(bpy.data.objects)
    try:
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            names = [
                name for name in data_from.objects
                if name.strip().lower() not in skip_names
            ]
            data_to.objects = names
            data_to.materials = list(data_from.materials)
            data_to.images = list(data_from.images)
    except OSError:
        return []
    return [
        obj for obj in bpy.data.objects
        if obj not in before and obj.type == "MESH"
    ]


def _group_under_empty(
    name: str,
    parts: list[bpy.types.Object],
    *,
    location: Vector,
    rotation: Optional[Vector] = None,
    scale: float = 1.0,
) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "SINGLE_ARROW"
    empty.location = location
    if rotation is not None:
        empty.rotation_euler = rotation
    if scale != 1.0:
        empty.scale = (scale, scale, scale)
    bpy.context.scene.collection.objects.link(empty)

    for part in parts:
        if not part.users_collection:
            bpy.context.scene.collection.objects.link(part)
        bpy.context.view_layer.update()
        world = part.matrix_world.copy()
        part.parent = empty
        part.matrix_world = world

    return empty


def _align_mesh_feet_to_root(root: bpy.types.Object, parts: list[bpy.types.Object]) -> None:
    """将 mesh 脚底对齐到 root 原点，便于 Follow Path 贴道路顶面。"""
    bpy.context.view_layer.update()
    min_local_z = 0.0
    found = False
    for part in parts:
        if part.type != "MESH":
            continue
        for vert in part.data.vertices:
            local = root.matrix_world.inverted() @ (part.matrix_world @ vert.co)
            if not found or local.z < min_local_z:
                min_local_z = local.z
                found = True
    if not found:
        return
    root.location.z -= min_local_z


def _yaw_car_assembly(
    root: bpy.types.Object,
    parts: list[bpy.types.Object],
    yaw: float,
) -> None:
    """绕 root 原点整体旋转车辆部件，避免逐件改 euler 导致车灯/保险杠错位。"""
    if abs(yaw) < 1e-6:
        return
    from mathutils import Matrix

    rot = Matrix.Rotation(yaw, 4, "Z")
    bpy.context.view_layer.update()
    pivot = root.matrix_world.translation.copy()
    translate_to_pivot = Matrix.Translation(pivot)
    translate_from_pivot = Matrix.Translation(-pivot)

    for part in parts:
        if part.type != "MESH":
            continue
        part.matrix_world = translate_to_pivot @ rot @ translate_from_pivot @ part.matrix_world


def _slot_z_bounds(
    obj: bpy.types.Object,
    slot_idx: int,
    root: bpy.types.Object,
) -> tuple[float, float] | None:
    zs: list[float] = []
    root_inv = root.matrix_world.inverted()
    for poly in obj.data.polygons:
        if poly.material_index != slot_idx:
            continue
        for vert_idx in poly.vertices:
            world = obj.matrix_world @ obj.data.vertices[vert_idx].co
            zs.append((root_inv @ world).z)
    if not zs:
        return None
    return min(zs), max(zs)


def _find_body_part(parts: list[bpy.types.Object]) -> bpy.types.Object | None:
    for part in parts:
        stem = part.name.split("_")[-1].strip().lower()
        if stem == "body":
            return part
    return None


def _fix_car_light_materials(parts: list[bpy.types.Object]) -> None:
    """Front light 等部件常误挂 Wheels 金属材质，视口会像悬浮碎件。"""
    body = _find_body_part(parts)
    body_mat = None
    if body and body.material_slots and body.material_slots[0].material:
        body_mat = body.material_slots[0].material

    for part in parts:
        if part.type != "MESH" or "light" not in part.name.lower():
            continue
        for slot in part.material_slots:
            mat = slot.material
            if mat is None:
                continue
            if mat.name in {"Wheels", "Tyre", "Screens", "Glass"} and body_mat is not None:
                slot.material = body_mat


def _align_car_lamp_parts(root: bpy.types.Object, parts: list[bpy.types.Object]) -> None:
    """将前/后灯组轻微下压，与车身格栅/尾部高度对齐，消除轻微悬空感。"""
    body = _find_body_part(parts)
    if body is None:
        return

    grill_idx = next(
        (
            i for i, slot in enumerate(body.material_slots)
            if slot.material and "grill" in slot.material.name.lower()
        ),
        None,
    )
    grill_bounds = (
        _slot_z_bounds(body, grill_idx, root)
        if grill_idx is not None
        else _slot_z_bounds(body, 0, root)
    )
    if grill_bounds is None:
        return
    grill_max_z = grill_bounds[1]

    for part in parts:
        name_lower = part.name.lower()
        if part.type != "MESH" or "light" not in name_lower or "rear" in name_lower:
            continue
        lamp_idx = next(
            (
                i for i, slot in enumerate(part.material_slots)
                if slot.material and slot.material.name.lower() in {"light", "lights"}
            ),
            None,
        )
        bounds = (
            _slot_z_bounds(part, lamp_idx, root)
            if lamp_idx is not None
            else _slot_z_bounds(part, 0, root)
        )
        if bounds is None:
            continue
        dz = grill_max_z - bounds[1]
        if abs(dz) > 1e-4:
            part.location.z += dz


def _append_car_rig(
    model_id: str,
    tag: str,
    context: bpy.types.Context,
) -> tuple[Optional[bpy.types.Object], list[bpy.types.Object]]:
    blend_path = car_blend_path(model_id)
    parts = _append_car_blend_objects(blend_path)
    if not parts:
        return None, []

    search_dirs = car_texture_search_dirs(model_id, blend_path)

    for part in parts:
        if not part.name.startswith(f"{SCG_CAR_PREFIX}{tag}_"):
            part.name = f"{SCG_CAR_PREFIX}{tag}_{part.name.strip()}"

    root = _group_under_empty(
        f"{SCG_CAR_PREFIX}{tag}",
        parts,
        location=Vector((0.0, 0.0, 0.0)),
    )
    _yaw_car_assembly(root, parts, _CAR_MESH_YAW_CORRECTION)
    _fix_car_light_materials(parts)
    _align_car_lamp_parts(root, parts)
    _align_mesh_feet_to_root(root, parts)
    _relink_textures_in_objects(parts, search_dirs)
    _apply_car_texture_fallbacks(parts)
    return root, parts


def _pedestrian_mesh_parts(root_obj: bpy.types.Object | None, new_objs: list[bpy.types.Object]) -> list[bpy.types.Object]:
    if root_obj is not None:
        if root_obj.type == "MESH":
            return [root_obj]
        meshes = [c for c in root_obj.children_recursive if c.type == "MESH"]
        if meshes:
            return meshes
    return [o for o in new_objs if o.type == "MESH"]


def _append_pedestrian(tag: str, people_index: int) -> Optional[bpy.types.Object]:
    if not _ensure_people_blend_library():
        return None

    obj_name = f"Collection of people x 5 04-{people_index:03d}"
    before = set(bpy.data.objects)
    try:
        with bpy.data.libraries.load(PEOPLE_BLEND, link=False) as (data_from, data_to):
            if obj_name not in data_from.objects:
                return None
            data_to.objects = [obj_name]
    except OSError:
        return None

    new_objs = [o for o in bpy.data.objects if o not in before]
    person = bpy.data.objects.get(obj_name)
    if person is None and new_objs:
        person = new_objs[0]
    if person is None:
        return None

    if person.name not in bpy.context.view_layer.objects:
        bpy.context.scene.collection.objects.link(person)

    parts = _pedestrian_mesh_parts(person, new_objs)
    if not parts:
        return None

    for part in parts:
        part.name = f"{SCG_PED_PREFIX}{tag}_{part.name.strip()}"
    # people.blend 导入时自带 0.01 缩放，先归一化再按目标身高缩放
    for part in parts:
        part.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    scale = _PED_TARGET_HEIGHT / _PED_NATIVE_HEIGHT
    for part in parts:
        part.scale = (scale, scale, scale)
    root = _group_under_empty(
        f"{SCG_PED_PREFIX}{tag}",
        parts,
        location=Vector((0.0, 0.0, 0.0)),
    )
    _yaw_car_assembly(root, parts, _PED_MESH_YAW_CORRECTION)
    _align_mesh_feet_to_root(root, parts)
    search_dirs = people_texture_search_dirs(PEOPLE_BLEND)
    _relink_textures_in_objects(parts, search_dirs)
    _apply_people_texture_fallbacks(parts)
    return root


def _boat_mesh_height_in_root(root: bpy.types.Object, parts: list[bpy.types.Object]) -> float:
    bpy.context.view_layer.update()
    min_z = 1e18
    max_z = -1e18
    found = False
    for part in parts:
        if part.type != "MESH":
            continue
        for vert in part.data.vertices:
            local = root.matrix_world.inverted() @ (part.matrix_world @ vert.co)
            min_z = min(min_z, local.z)
            max_z = max(max_z, local.z)
            found = True
    if not found or max_z <= min_z:
        return 0.0
    return max_z - min_z


def _boat_float_z_offset(root: bpy.types.Object, parts: list[bpy.types.Object]) -> float:
    """抬高船体，使吃水线贴水面而非半淹。"""
    height = _boat_mesh_height_in_root(root, parts)
    if height <= 1e-4:
        return 0.0
    return height * _BOAT_WATERLINE_RATIO


def _scale_boat_to_length(root: bpy.types.Object, parts: list[bpy.types.Object], target_length: float) -> None:
    bpy.context.view_layer.update()
    bounds_min = Vector((1e18, 1e18, 1e18))
    bounds_max = Vector((-1e18, -1e18, -1e18))
    for part in parts:
        if part.type != "MESH":
            continue
        for corner in part.bound_box:
            world = part.matrix_world @ Vector(corner)
            bounds_min = Vector((min(bounds_min[i], world[i]) for i in range(3)))
            bounds_max = Vector((max(bounds_max[i], world[i]) for i in range(3)))
    size = bounds_max - bounds_min
    length = max(size.x, size.y, 0.01)
    if length < 0.01:
        return
    factor = target_length / length
    root.scale = (factor, factor, factor)


def _append_boat_rig(tag: str, context: bpy.types.Context) -> tuple[Optional[bpy.types.Object], list[bpy.types.Object]]:
    if not os.path.isfile(BOAT_BLEND):
        return None, []

    skip_names = {"camera", "cube", "light", "plane"}
    before = set(bpy.data.objects)
    try:
        with bpy.data.libraries.load(BOAT_BLEND, link=False) as (data_from, data_to):
            names = [
                name for name in data_from.objects
                if name.strip().lower() not in skip_names
            ]
            if BOAT_OBJECT_NAME in data_from.objects and BOAT_OBJECT_NAME not in names:
                names.insert(0, BOAT_OBJECT_NAME)
            data_to.objects = names
            data_to.materials = list(data_from.materials)
            data_to.images = list(data_from.images)
    except OSError:
        return None, []

    parts = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not parts:
        return None, []

    for part in parts:
        if not part.name.startswith(f"{SCG_BOAT_PREFIX}{tag}_"):
            part.name = f"{SCG_BOAT_PREFIX}{tag}_{part.name.strip()}"

    root = _group_under_empty(
        f"{SCG_BOAT_PREFIX}{tag}",
        parts,
        location=Vector((0.0, 0.0, 0.0)),
    )
    _yaw_car_assembly(root, parts, _BOAT_MESH_YAW_CORRECTION)
    _scale_boat_to_length(root, parts, _BOAT_TARGET_LENGTH_M)
    _align_mesh_feet_to_root(root, parts)
    root["scg_boat_float_z"] = _boat_float_z_offset(root, parts)
    root.empty_display_size = 0.001
    _ = context
    return root, parts


def _duplicate_boat_rig(
    source_root: bpy.types.Object,
    source_parts: list[bpy.types.Object],
    tag: str,
) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    new_parts: list[bpy.types.Object] = []
    for part in source_parts:
        stem = part.name.split("_")[-1]
        dup = part.copy()
        if dup.data is not None:
            dup.data = dup.data.copy()
        dup.name = f"{SCG_BOAT_PREFIX}{tag}_{stem}"
        new_parts.append(dup)
    root = _group_under_empty(
        f"{SCG_BOAT_PREFIX}{tag}",
        new_parts,
        location=Vector((0.0, 0.0, 0.0)),
    )
    root.scale = source_root.scale.copy()
    root["scg_boat_float_z"] = source_root.get("scg_boat_float_z", 0.0)
    root.empty_display_size = 0.001
    return root, new_parts


def _build_car_loop_paths(
    loop_segments: list[tuple[Vector, Vector]],
    loop_center: Vector,
    half_lane: float,
    surface_z: float,
) -> tuple[bpy.types.Object, bpy.types.Object, bool]:
    """返回 (CW 路径, CCW 路径, 是否使用手动画/路径库曲线)。"""
    manual_cw = find_manual_path(MANUAL_PATH_CAR_CW)
    manual_ccw = find_manual_path(MANUAL_PATH_CAR_CCW)
    if manual_cw is not None and manual_ccw is not None:
        link_path_to_collection(manual_cw)
        link_path_to_collection(manual_ccw)
        return manual_cw, manual_ccw, True

    path_cw = create_lane_loop_curve(
        "SCG_Path_Car_Loop_CW",
        loop_segments,
        lateral_offset=half_lane,
        surface_z=surface_z,
        loop_center=loop_center,
        lane_band=1.0,
        reverse=False,
    )
    link_path_to_collection(path_cw)
    path_ccw = create_lane_loop_curve(
        "SCG_Path_Car_Loop_CCW",
        loop_segments,
        lateral_offset=half_lane,
        surface_z=surface_z,
        loop_center=loop_center,
        lane_band=-1.0,
        reverse=False,
    )
    link_path_to_collection(path_ccw)
    return path_cw, path_ccw, False


def _build_ped_sidewalk_paths(
    loop_segments: list[tuple[Vector, Vector]],
    loop_center: Vector,
    sidewalk_offset: float,
    surface_z: float,
    *,
    car_cw: bpy.types.Object | None = None,
    car_ccw: bpy.types.Object | None = None,
    sidewalk_width: float = 2.5,
    half_lane: float = 1.75,
) -> tuple[list[bpy.types.Object], str]:
    """
    返回 ([外CW, 外CCW, 内CW, 内CCW], 路径来源说明)。
    优先沿路径库机动车道曲线偏移生成人行道，保证不进入车道。
    """
    if car_cw is not None and car_ccw is not None:
        try:
            inner, outer = create_pedestrian_paths_from_lane_curves(
                car_cw,
                car_ccw,
                half_lane=half_lane,
                sidewalk_width=sidewalk_width,
                surface_z=surface_z,
                loop_center=loop_center,
            )
            link_path_to_collection(inner)
            link_path_to_collection(outer)
            return [outer, outer, inner, inner], "沿路径库车道偏移"
        except (ValueError, TypeError):
            pass

    paths: list[bpy.types.Object] = []
    specs = (
        ("SCG_Path_Ped_Outer_CW", True, False),
        ("SCG_Path_Ped_Outer_CCW", True, True),
        ("SCG_Path_Ped_Inner_CW", False, False),
        ("SCG_Path_Ped_Inner_CCW", False, True),
    )
    for name, outer, reverse in specs:
        curve = create_sidewalk_loop_curve(
            name,
            loop_segments,
            lateral_offset=sidewalk_offset,
            surface_z=surface_z,
            loop_center=loop_center,
            outer=outer,
            reverse=reverse,
        )
        link_path_to_collection(curve)
        paths.append(curve)
    return paths, "道路环路自动生成"


def try_auto_add_dynamic_elements(
    context: bpy.types.Context,
    scene: bpy.types.Scene | None = None,
) -> str:
    """生成/应用布局后自动布置车辆与行人；失败时返回说明，成功返回摘要。"""
    if scene is None:
        scene = context.scene
    if not icity_scene_ready():
        return "（动态元素跳过：未 Start）"

    car_count = int(getattr(scene, "scg_car_count", 0))
    ped_count = int(getattr(scene, "scg_pedestrian_count", 0))
    if car_count <= 0 and ped_count <= 0:
        return ""

    try:
        context.view_layer.update()
        bpy.context.evaluated_depsgraph_get().update()
    except (AttributeError, RuntimeError):
        pass

    ok, message = add_cars_and_pedestrians(context)
    if ok:
        return f" | {message}"
    return f" | 动态元素：{message}"


def add_cars_and_pedestrians(
    context: bpy.types.Context,
) -> Tuple[bool, str]:
    """按面板参数添加车辆与行人路径动画（不依赖山水）。"""
    if not icity_scene_ready():
        return False, "请先 Start 并生成基础城市"

    scene = context.scene
    model_id = getattr(scene, "scg_car_model", "BMW")
    car_count = int(getattr(scene, "scg_car_count", 2))
    ped_count = int(getattr(scene, "scg_pedestrian_count", 3))

    if car_count <= 0 and ped_count <= 0:
        return False, "车辆与行人数量均为 0"

    if car_count > 0 and not car_model_available(model_id):
        return False, f"未找到车辆模型：{car_blend_path(model_id)}"
    if ped_count > 0 and not people_asset_available():
        return False, f"未找到行人资产：{PEOPLE_BLEND}"

    _ensure_object_mode(context)
    ensure_manual_car_paths_in_scene(context)

    replaced = len(_car_ped_objects()) > 0
    cleanup_cars_and_pedestrians()

    loop_segments = extract_street_loop()
    if not loop_segments:
        cleanup_cars_and_pedestrians()
        return False, "未找到可用道路环路（请先生成基础城市）"

    loop_center = _loop_center(loop_segments)

    cross_section = get_road_cross_section()
    half_lane = cross_section["half_lane"]
    sidewalk_width = cross_section["sidewalk_width"]
    sidewalk_center = cross_section["sidewalk_center"]
    surface_z = get_road_surface_z()
    frame_start, frame_end = get_animation_frame_range(scene)
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    car_loops = _CAR_LOOP_PROGRESS
    ped_loops = car_loops * _PED_SPEED_RATIO

    _ensure_collection(SCG_DYNAMICS_COLLECTION)
    placed_cars = 0
    placed_peds = 0

    path_cw: bpy.types.Object | None = None
    path_ccw: bpy.types.Object | None = None
    ped_paths: list[bpy.types.Object] = []
    car_path_source = "自动"
    ped_path_source = "自动"

    if car_count > 0:
        path_cw, path_ccw, car_manual = _build_car_loop_paths(
            loop_segments, loop_center, half_lane, surface_z,
        )
        car_path_source = "路径库" if car_manual else "自动"

    if ped_count > 0:
        ped_paths, ped_path_source = _build_ped_sidewalk_paths(
            loop_segments,
            loop_center,
            sidewalk_center,
            surface_z,
            car_cw=path_cw,
            car_ccw=path_ccw,
            sidewalk_width=sidewalk_width,
            half_lane=half_lane,
        )

    unique_paths: list[bpy.types.Object] = []
    for path in filter(None, [path_cw, path_ccw, *ped_paths]):
        if path not in unique_paths:
            unique_paths.append(path)
    for path in unique_paths:
        prepare_path_curve_for_animation(path, surface_z)

    for i in range(car_count):
        tag = f"{i + 1:02d}"
        car_root, parts = _append_car_rig(model_id, tag, context)
        if car_root is None or path_cw is None or path_ccw is None:
            continue
        clockwise = i % 2 == 0
        path = path_cw if clockwise else path_ccw
        spacing = 1.0 / max(car_count, 1)
        add_follow_path_animation(
            car_root,
            path,
            frame_start=frame_start,
            frame_end=frame_end,
            offset_start=((i + 0.5) * spacing) % 1.0,
            loops=car_loops,
            forward_axis=_CAR_FORWARD_AXIS,
            forward_local=_CAR_FORWARD_LOCAL,
            reverse_path=True,
            surface_z=surface_z,
            dense_motion=True,
        )
        _move_rig_to_collection(car_root, parts, SCG_DYNAMICS_COLLECTION)
        placed_cars += 1

    people_ids = [1, 2, 3, 4, 5, 6]
    for i in range(ped_count):
        tag = f"{i + 1:02d}"
        ped_root = _append_pedestrian(tag, people_ids[i % len(people_ids)])
        if ped_root is None or not ped_paths:
            continue
        on_outer = i % 2 == 0
        direction_idx = (i // 2) % 2
        path_idx = direction_idx if on_outer else 2 + direction_idx
        if path_idx >= len(ped_paths):
            continue
        path = ped_paths[path_idx]
        reverse_walk = direction_idx == 1
        ped_forward = _PED_FORWARD_LOCAL if on_outer else _PED_INNER_FORWARD_LOCAL
        if reverse_walk:
            ped_forward = Vector((-ped_forward.x, -ped_forward.y, 0.0))
        spacing = 1.0 / max(ped_count, 1)
        add_follow_path_animation(
            ped_root,
            path,
            frame_start=frame_start,
            frame_end=frame_end,
            offset_start=(i * spacing + spacing * 0.15) % 1.0,
            loops=ped_loops,
            forward_axis=_PED_FORWARD_AXIS,
            forward_local=ped_forward,
            reverse_path=reverse_walk,
            surface_z=surface_z,
        )
        _move_to_collection([ped_root, *ped_root.children_recursive], SCG_DYNAMICS_COLLECTION)
        placed_peds += 1

    if placed_cars == 0 and placed_peds == 0:
        cleanup_cars_and_pedestrians()
        return False, "车辆/行人添加失败，请检查资产路径"

    _flush_viewport_refresh()
    scene.frame_set(frame_start)
    replace_note = "（已替换旧实例）" if replaced else ""
    ped_note = ""
    if placed_peds < ped_count:
        ped_note = f"（行人请求 {ped_count}，成功 {placed_peds}）"
    return True, (
        f"已添加车辆与行人{replace_note}：车辆 {placed_cars}（双向机动车道靠右）、"
        f"行人 {placed_peds}{ped_note}（里/外人行道）；"
        f"车道路径={car_path_source} / 人行道={ped_path_source}；"
        f"车道半宽 {half_lane:.1f}m / 人行道 {sidewalk_center:.1f}m；"
        f"动画 {frame_start}–{frame_end} 帧，按空格播放"
    )


def add_boats(context: bpy.types.Context) -> Tuple[bool, str]:
    """在湖面添加船只环绕动画（需先添加中央山水）。"""
    if not icity_scene_ready():
        return False, "请先 Start 并生成基础城市"

    scene = context.scene
    boat_count = int(getattr(scene, "scg_boat_count", 1))
    if boat_count <= 0:
        return False, "船只数量为 0"

    if not boat_asset_available():
        return False, f"未找到船只资产：{BOAT_BLEND}"
    if not landscape_surround_exists():
        return False, "添加船只需先「添加中央山水」"

    _ensure_object_mode(context)

    replaced = len(_boat_objects()) > 0
    cleanup_boats()

    water_z = get_water_surface_z()
    if water_z is None:
        cleanup_boats()
        return False, "无法读取湖面高度"

    ensure_manual_boat_path_in_scene(context)
    manual_boat = find_manual_path(MANUAL_PATH_BOAT)
    using_manual_boat = manual_boat is not None
    if using_manual_boat:
        boat_path = manual_boat
        path_source = "手动画曲线 SCG_Manual_Boat"
        prepare_manual_boat_path_for_animation(boat_path, water_z)
        boat_loops = _MANUAL_BOAT_LOOP_PROGRESS
    else:
        boat_path = create_boat_water_loop_curve()
        path_source = "自动湖面环线"
        if boat_path is not None:
            link_path_to_collection(boat_path)
            if boat_path.data is not None:
                boat_path.data.use_path = True
                for spline in boat_path.data.splines:
                    spline.use_cyclic_u = True
            prepare_path_curve_for_animation(boat_path, water_z)
        boat_loops = _CAR_LOOP_PROGRESS * _BOAT_SPEED_RATIO
    if boat_path is None:
        cleanup_boats()
        return False, (
            "无法生成船行路径：请保存 SCG_Manual_Boat 到路径库，"
            "或确认已添加中央山水"
        )

    frame_start, frame_end = get_animation_frame_range(scene)
    scene.frame_start = frame_start
    scene.frame_end = frame_end

    _ensure_collection(SCG_DYNAMICS_COLLECTION)
    placed_boats = 0
    if using_manual_boat:
        boat_offsets = distributed_boat_path_offsets(boat_path, boat_count)
    else:
        min_gap = max(0.12, 0.85 / max(boat_count, 1))
        boat_offsets = random_spaced_path_offsets(boat_count, min_gap=min_gap)

    template_root, template_parts = _append_boat_rig("01", context)
    if template_root is None:
        cleanup_boats()
        return False, "船只添加失败，请检查资产路径"

    boat_instances: list[tuple[bpy.types.Object, list[bpy.types.Object]]] = [
        (template_root, template_parts),
    ]
    for i in range(1, boat_count):
        tag = f"{i + 1:02d}"
        boat_instances.append(_duplicate_boat_rig(template_root, template_parts, tag))

    for i, (boat_root, parts) in enumerate(boat_instances):
        offset = boat_offsets[i] if i < len(boat_offsets) else ((i + 0.5) / max(boat_count, 1)) % 1.0
        animated = add_follow_path_animation(
            boat_root,
            boat_path,
            frame_start=frame_start,
            frame_end=frame_end,
            offset_start=offset,
            loops=boat_loops,
            forward_local=_BOAT_FORWARD_LOCAL,
            reverse_path=False,
            surface_z=None,
            skip_center_guard=True,
            dense_motion=using_manual_boat,
            snap_water_surface=True,
            water_fallback_z=water_z,
            boat_offset_final=using_manual_boat,
        )
        if not animated:
            bpy.data.objects.remove(boat_root, do_unlink=True)
            for part in parts:
                bpy.data.objects.remove(part, do_unlink=True)
            continue
        _move_rig_to_collection(boat_root, parts, SCG_DYNAMICS_COLLECTION)
        placed_boats += 1

    if placed_boats == 0:
        cleanup_boats()
        return False, "船只添加失败，请检查资产路径"

    _flush_viewport_refresh()
    scene.frame_set(frame_start)
    for obj in context.view_layer.objects:
        obj.select_set(False)
    context.view_layer.update()
    replace_note = "（已替换旧实例）" if replaced else ""
    return True, (
        f"已添加船只{replace_note}：{placed_boats} 艘（{path_source}，均匀分布）；"
        f"动画 {frame_start}–{frame_end} 帧，按空格播放"
    )
