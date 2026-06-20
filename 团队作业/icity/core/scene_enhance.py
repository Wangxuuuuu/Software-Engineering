"""
场景增强：山水生态等（阶段三 B）。

动态元素（车辆/行人/船只动画）在阶段 C 扩展。
"""

from __future__ import annotations

import math
import os
import random
from typing import Iterable, Optional, Tuple

import bpy
from mathutils import Vector

from .assets_manager import (
    LAKE_BLEND,
    LAKE_TEXTURE_SEARCH_DIRS,
    LAKE_TERRAIN_COLLECTION,
    LAKE_TREES_COLLECTION,
    lake_landscape_asset_available,
)
from .city_generator import _flush_viewport_refresh, icity_scene_ready

SCG_ECOLOGY_COLLECTION = "SCG_Ecology"
SCG_LANDSCAPE_ROOT = "SCG_Landscape_Surround"
SCG_LANDSCAPE_GROUP = "SCG_Landscape_Group"
# 导入后重命名，避免与场景内已有 Terrain/Trees 集合冲突
SCG_LAKE_TERRAIN_COLL = "SCG_Lake_Terrain"
SCG_LAKE_TREES_COLL = "SCG_Lake_Trees"

# 水面相对城市宽度的放大倍率（>1 表示城市完全落在水中央并留余量）
_WATER_CITY_MARGIN = 1.35
# 水面 Z 相对道路底面的偏移（米）；负值=水面更低，避免少量浸水
_WATER_SURFACE_OFFSET_M = -0.05
# 岸边树高度 = 城市最高建筑高度 × 该比例（且绝不超过建筑高度）
_SHORE_TREE_HEIGHT_RATIO = 0.42
# 沿水面岸线在原有树基础上额外均匀复制一圈（1.0=约翻倍）
_SHORE_TREE_DENSITY_FACTOR = 1.6
# 树木离城市 XY 中心的最小水平距离（相对城市跨度）
_SHORE_TREE_MIN_CITY_CLEARANCE_RATIO = 0.38


def _ensure_collection(name: str, parent: Optional[bpy.types.Collection] = None) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        if parent is not None:
            parent.children.link(coll)
        else:
            bpy.context.scene.collection.children.link(coll)
    return coll


def _move_objects_to_collection(objects: Iterable[bpy.types.Object], collection_name: str) -> None:
    coll = _ensure_collection(collection_name)
    for obj in objects:
        for user_coll in list(obj.users_collection):
            user_coll.objects.unlink(obj)
        coll.objects.link(obj)


def _iter_material_images(obj: bpy.types.Object):
    mats = {slot.material for slot in obj.material_slots if slot.material}
    for child in obj.children:
        mats.update(slot.material for slot in child.material_slots if slot.material)
    for mat in mats:
        if mat is None or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                yield node


def _relink_textures_in_objects(
    objects: Iterable[bpy.types.Object],
    search_dirs: tuple[str, ...],
) -> int:
    fixed = 0
    for obj in objects:
        for node in _iter_material_images(obj):
            img = node.image
            names: list[str] = []
            if img.filepath:
                try:
                    if os.path.isfile(bpy.path.abspath(img.filepath)):
                        continue
                except ValueError:
                    pass
                names.append(os.path.basename(bpy.path.abspath(img.filepath)))
            names.append(img.name)
            if "." not in img.name:
                names.append(f"{img.name}.png")
                names.append(f"{img.name}.jpeg")
                names.append(f"{img.name}.jpg")

            resolved: str | None = None
            for base in names:
                if not base:
                    continue
                for search_dir in search_dirs:
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


def _world_bounds(objects: Iterable[bpy.types.Object]) -> Optional[Tuple[Vector, Vector]]:
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    count = 0
    for obj in objects:
        if obj.type not in {"MESH", "CURVE", "EMPTY"}:
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            mins = Vector((min(mins[i], world[i]) for i in range(3)))
            maxs = Vector((max(maxs[i], world[i]) for i in range(3)))
            count += 1
    if count == 0:
        return None
    return mins, maxs


def _bounds_from_evaluated_mesh(obj: bpy.types.Object) -> Optional[Tuple[Vector, Vector]]:
    """读取几何节点刷新后的真实网格范围（ICity Road 等）。"""
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        mesh = ev.to_mesh()
    except (RuntimeError, AttributeError):
        return None
    if not mesh or not mesh.vertices:
        try:
            ev.to_mesh_clear()
        except Exception:
            pass
        return None
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    for vert in mesh.vertices:
        world = obj.matrix_world @ vert.co
        mins = Vector((min(mins[i], world[i]) for i in range(3)))
        maxs = Vector((max(maxs[i], world[i]) for i in range(3)))
    try:
        ev.to_mesh_clear()
    except Exception:
        pass
    return mins, maxs


def _icity_scene_objects() -> list[bpy.types.Object]:
    objs: list[bpy.types.Object] = []
    for name in (
        "ICity Road",
        "ICity building procedural base",
        "ICity Procedural ground",
        "ICity Spces",
        "ICity Base",
    ):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            objs.append(obj)
    proc = bpy.data.collections.get("ICity_Procedural")
    if proc:
        objs.extend(proc.all_objects)
    return objs


def get_city_bounds() -> Optional[Tuple[Vector, Vector, Vector]]:
    """
    返回 (center, half_extents, size)。

    ICity Base 编辑网格仅 ~0.1m，真实城市范围来自 Road / 建筑几何节点输出。
    """
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    found = False

    road = bpy.data.objects.get("ICity Road")
    if road is not None:
        road_bounds = _bounds_from_evaluated_mesh(road)
        if road_bounds is not None:
            rmin, rmax = road_bounds
            mins = Vector((min(mins[i], rmin[i]) for i in range(3)))
            maxs = Vector((max(maxs[i], rmax[i]) for i in range(3)))
            found = True

    obj_bounds = _world_bounds(_icity_scene_objects())
    if obj_bounds is not None:
        omin, omax = obj_bounds
        mins = Vector((min(mins[i], omin[i]) for i in range(3)))
        maxs = Vector((max(maxs[i], omax[i]) for i in range(3)))
        found = True

    if not found:
        return None

    center = (mins + maxs) * 0.5
    size = maxs - mins
    half = size * 0.5
    return center, half, size


def get_city_ground_z() -> float:
    """
    城市地面参考高度（道路底面 Z + 偏移）。

    对齐道路顶面会让水面略高于 z≈0 的建筑底，出现少量浸水。
    """
    road = bpy.data.objects.get("ICity Road")
    if road is not None:
        road_bounds = _bounds_from_evaluated_mesh(road)
        if road_bounds is not None:
            return road_bounds[0].z + _WATER_SURFACE_OFFSET_M
        return road.matrix_world.translation.z + _WATER_SURFACE_OFFSET_M

    ground = bpy.data.objects.get("ICity Procedural ground")
    if ground is not None:
        return ground.matrix_world.translation.z + _WATER_SURFACE_OFFSET_M

    base = bpy.data.objects.get("ICity Base")
    if base is not None:
        return base.matrix_world.translation.z + _WATER_SURFACE_OFFSET_M

    return _WATER_SURFACE_OFFSET_M


def get_road_surface_z() -> float:
    """道路顶面 Z（车辆 / 行人路径与贴地参考）。"""
    road = bpy.data.objects.get("ICity Road")
    if road is not None:
        road_bounds = _bounds_from_evaluated_mesh(road)
        if road_bounds is not None:
            return road_bounds[1].z
        return road.matrix_world.translation.z

    return get_city_ground_z() - _WATER_SURFACE_OFFSET_M


def landscape_surround_exists() -> bool:
    return bpy.data.objects.get(SCG_LANDSCAPE_ROOT) is not None


def get_scg_water_objects() -> list[bpy.types.Object]:
    """中央山水水面网格（已放置 SCG_Landscape_Surround 后可用）。"""
    objs: list[bpy.types.Object] = []
    root = bpy.data.objects.get(SCG_LANDSCAPE_ROOT)
    if root is not None:
        for child in root.children_recursive:
            if child.type == "MESH" and "Water" in child.name:
                objs.append(child)
    if objs:
        return objs
    for obj in bpy.data.objects:
        if obj.type != "MESH" or "Water" not in obj.name:
            continue
        if obj.name.startswith(SCG_LAKE_TERRAIN_COLL) or "SCG_Lake" in obj.name:
            objs.append(obj)
    return objs


def get_water_surface_z() -> float | None:
    """湖面 Z（船只路径高度）；无山水时返回 None。"""
    water = get_scg_water_objects()
    if not water:
        return None
    bounds = _world_bounds(water)
    if bounds is None:
        return None
    return bounds[1].z - 0.08


def sample_water_shore_ring(water_objs: list[bpy.types.Object], samples: int) -> list[Vector]:
    """水面外缘环线采样（世界坐标）。"""
    return _water_shore_ring_points(water_objs, samples)


def get_water_xy_center(water_objs: list[bpy.types.Object] | None = None) -> Optional[Vector]:
    """湖面 XY 中心（用于船只环线）。"""
    objs = water_objs if water_objs is not None else get_scg_water_objects()
    if not objs:
        return None
    bounds = _world_bounds(objs)
    if bounds is None:
        return None
    center = (bounds[0] + bounds[1]) * 0.5
    return Vector((center.x, center.y, 0.0))


def sample_water_outer_shore_ring(water_objs: list[bpy.types.Object], samples: int) -> list[Vector]:
    """按极角分桶取最外缘顶点，避免路径抄近路穿过湖心。"""
    return _water_outer_shore_ring_points(water_objs, samples)


def get_city_xy_center() -> Optional[Vector]:
    """
    城市在 XY 平面的真实中心。

    ICity 道路/建筑几何节点输出常在原点附近，get_city_bounds() 的 center.xy
    会因实例偏移而偏离实际城市位置（导致山水与湖心错位）。
    """
    proc = bpy.data.collections.get("ICity_Procedural")
    if proc is not None and proc.all_objects:
        proc_bounds = _world_bounds(proc.all_objects)
        if proc_bounds is not None:
            pmin, pmax = proc_bounds
            center = (pmin + pmax) * 0.5
            return Vector((center.x, center.y, 0.0))

    road = bpy.data.objects.get("ICity Road")
    if road is not None:
        road_bounds = _bounds_from_evaluated_mesh(road)
        if road_bounds is not None:
            rmin, rmax = road_bounds
            center = (rmin + rmax) * 0.5
            return Vector((center.x, center.y, 0.0))

    city = get_city_bounds()
    if city is not None:
        center, _, _ = city
        return Vector((center.x, center.y, 0.0))

    return None


def get_landscape_xy_center() -> Optional[Vector]:
    """湖心 XY：优先山水 root，否则回退城市中心。"""
    root = bpy.data.objects.get(SCG_LANDSCAPE_ROOT)
    if root is not None:
        return Vector((root.location.x, root.location.y, 0.0))
    return get_city_xy_center()


def point_xy_clear_of_city(x: float, y: float, clearance_m: float = 20.0) -> bool:
    """点是否在城市包围盒 + 安全距离之外。"""
    city = get_city_bounds()
    if city is None:
        return True
    center, half, _size = city
    return (
        abs(x - center.x) >= half.x + clearance_m
        or abs(y - center.y) >= half.y + clearance_m
    )


def min_boat_orbit_radius(clearance_m: float) -> float:
    """船只环线最小半径：城市外缘 + 安全距离。"""
    city = get_city_bounds()
    if city is None:
        return clearance_m
    _center, half, _size = city
    return max(half.x, half.y) + clearance_m


def water_surface_z_at_xy(
    x: float,
    y: float,
    water_objs: list[bpy.types.Object],
    fallback_z: float,
) -> float:
    """取指定 XY 附近水面顶面 Z（用于船只贴水面）。"""
    best_z = fallback_z
    best_d2 = 1e18
    for obj in water_objs:
        if obj.type != "MESH" or obj.data is None:
            continue
        for vert in obj.data.vertices:
            world = obj.matrix_world @ vert.co
            if world.z < fallback_z - 2.0:
                continue
            d2 = (world.x - x) ** 2 + (world.y - y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_z = world.z
    return best_z - 0.15


def _ensure_object_mode(context: bpy.types.Context) -> None:
    """wm.append / libraries.load 链接对象前须处于 Object 模式。"""
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _refresh_scene(context: bpy.types.Context) -> None:
    """父子级缩放后刷新变换，避免包围盒仍按未缩放矩阵计算。"""
    try:
        context.view_layer.update()
    except (AttributeError, RuntimeError):
        pass
    try:
        dg = context.evaluated_depsgraph_get()
        dg.update()
    except (AttributeError, RuntimeError):
        pass


def _collection_names_in_blend(blend_path: str) -> set[str]:
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, _data_to):
        return set(data_from.collections)


def _append_collection_from_blend(
    blend_path: str,
    collection_name: str,
    *,
    import_as: str,
    context: bpy.types.Context,
) -> tuple[Optional[bpy.types.Collection], list[bpy.types.Object]]:
    """
    用 libraries.load 追加集合（比 wm.append 更稳，不依赖 Edit/Object 上下文）。
    返回 (集合, 集合内全部对象)。
    """
    if not os.path.isfile(blend_path):
        return None, []

    available = _collection_names_in_blend(blend_path)
    if collection_name not in available:
        return None, []

    before_colls = set(bpy.data.collections)
    before_objs = set(bpy.data.objects)

    try:
        with bpy.data.libraries.load(blend_path, link=False) as (_data_from, data_to):
            data_to.collections = [collection_name]
    except OSError:
        return None, []

    new_colls = [c for c in bpy.data.collections if c not in before_colls]
    coll = next((c for c in new_colls if c.name == collection_name), None)
    if coll is None:
        coll = bpy.data.collections.get(collection_name)
    if coll is None and new_colls:
        coll = new_colls[0]
    if coll is None:
        return None, []

    unique_name = import_as
    if bpy.data.collections.get(unique_name) and bpy.data.collections.get(unique_name) != coll:
        idx = 1
        while bpy.data.collections.get(f"{unique_name}.{idx:03d}"):
            idx += 1
        unique_name = f"{unique_name}.{idx:03d}"
    coll.name = unique_name

    ecology = _ensure_collection(SCG_ECOLOGY_COLLECTION)
    if coll.name not in ecology.children:
        try:
            ecology.children.link(coll)
        except RuntimeError:
            pass

    new_objs = [o for o in bpy.data.objects if o not in before_objs]
    if not new_objs:
        new_objs = list(coll.all_objects)
    return coll, new_objs


def _build_landscape_objects(
    blend_path: str,
    context: bpy.types.Context,
) -> tuple[list[bpy.types.Object], list[bpy.types.Object]]:
    """追加 Terrain（水面+地面）与 Trees（岸边树，后续会缩放并沿岸线均匀分布）。"""
    _ensure_object_mode(context)
    terrain_objs: list[bpy.types.Object] = []
    tree_objs: list[bpy.types.Object] = []
    _coll, patch = _append_collection_from_blend(
        blend_path,
        LAKE_TERRAIN_COLLECTION,
        import_as=SCG_LAKE_TERRAIN_COLL,
        context=context,
    )
    if patch:
        terrain_objs.extend(patch)
    _coll2, trees = _append_collection_from_blend(
        blend_path,
        LAKE_TREES_COLLECTION,
        import_as=SCG_LAKE_TREES_COLL,
        context=context,
    )
    if trees:
        tree_objs.extend(trees)
    return terrain_objs, tree_objs


def _object_in_trees_collection(obj: bpy.types.Object) -> bool:
    """LowPolyTrees.blend 的 Leaves/Bark 网格在 SCG_Lake_Trees 集合内。"""
    for coll in obj.users_collection:
        if coll.name.startswith(SCG_LAKE_TREES_COLL):
            return True
    return False


def _is_tree_object(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    name = obj.name.lower()
    if any(k in name for k in ("water", "ground", "terrain")):
        return False
    if _object_in_trees_collection(obj):
        return True
    return any(
        k in name
        for k in ("tree", "pine", "bush", "shrub", "plant", "leaves", "bark")
    ) or obj.name.startswith(SCG_LAKE_TREES_COLL)


def _estimate_building_height() -> float:
    city = get_city_bounds()
    if city is not None:
        _center, _half, size = city
        return max(size.z * 0.55, 12.0)
    return 15.0


def _measure_max_building_height(ground_z: float | None = None) -> float:
    """测量城市最高建筑相对地面的高度（米）。"""
    if ground_z is None:
        ground_z = get_city_ground_z()

    max_top_z = ground_z + 6.0
    found = False

    proc = bpy.data.collections.get("ICity_Procedural")
    if proc is not None:
        for obj in proc.all_objects:
            if obj.type != "MESH":
                continue
            bounds = _world_bounds([obj])
            if bounds is None:
                continue
            max_top_z = max(max_top_z, bounds[1].z)
            found = True

    building_base = bpy.data.objects.get("ICity building procedural base")
    if building_base is not None:
        bounds = _bounds_from_evaluated_mesh(building_base)
        if bounds is not None:
            max_top_z = max(max_top_z, bounds[1].z)
            found = True

    height = max_top_z - ground_z
    if not found or height < 3.0:
        height = _estimate_building_height()
    return max(height, 6.0)


def _shore_tree_target_height(ground_z: float) -> float:
    """岸边树目标高度：不超过城市最高楼。"""
    building_h = _measure_max_building_height(ground_z)
    target = building_h * _SHORE_TREE_HEIGHT_RATIO
    return min(target, building_h)


def _object_height(obj: bpy.types.Object) -> float:
    bounds = _world_bounds([obj])
    if bounds is None:
        return 0.0
    return bounds[1].z - bounds[0].z


def _rig_world_height(root: bpy.types.Object) -> float:
    bounds = _world_bounds(_tree_rig_objects(root))
    if bounds is None:
        return 0.0
    return bounds[1].z - bounds[0].z


def _scale_shore_trees_to_height(tree_objs: list[bpy.types.Object], target_height: float) -> None:
    """按世界空间高度缩放树木（仅缩放 Bark 根，Leaves 随父级）。"""
    if target_height <= 0.01:
        return
    for root in _tree_bark_roots(tree_objs):
        h = _rig_world_height(root)
        if h < 0.01:
            continue
        factor = target_height / h
        root.scale = Vector((root.scale.x * factor, root.scale.y * factor, root.scale.z * factor))


def _cap_trees_world_height(tree_objs: list[bpy.types.Object], max_height: float) -> None:
    """硬上限：确保树高不超过城市建筑。"""
    if max_height <= 0.01:
        return
    for root in _tree_bark_roots(tree_objs):
        h = _rig_world_height(root)
        if h > max_height * 1.02:
            factor = max_height / h
            root.scale = Vector((root.scale.x * factor, root.scale.y * factor, root.scale.z * factor))


def _water_shore_ring_points(water_objs: list[bpy.types.Object], samples: int) -> list[Vector]:
    """取水面顶面附近顶点，按极角排序作为岸线采样。"""
    ring: list[Vector] = []
    for obj in water_objs:
        if obj.type != "MESH" or obj.data is None:
            continue
        bounds = _world_bounds([obj])
        if bounds is None:
            continue
        z_top = bounds[1].z - 0.05
        for vert in obj.data.vertices:
            world = obj.matrix_world @ vert.co
            if world.z >= z_top - 0.35:
                ring.append(Vector((world.x, world.y, world.z)))
    if len(ring) < 8:
        return []
    center = sum(ring, Vector()) / len(ring)
    ring.sort(key=lambda p: math.atan2(p.y - center.y, p.x - center.x))
    if len(ring) <= samples:
        return ring
    step = len(ring) / samples
    return [ring[int(i * step) % len(ring)] for i in range(samples)]


def _water_outer_shore_ring_points(water_objs: list[bpy.types.Object], samples: int) -> list[Vector]:
    """每极角扇区保留离湖心最远顶点，得到真实外岸线。"""
    candidates: list[Vector] = []
    for obj in water_objs:
        if obj.type != "MESH" or obj.data is None:
            continue
        bounds = _world_bounds([obj])
        if bounds is None:
            continue
        z_top = bounds[1].z - 0.05
        for vert in obj.data.vertices:
            world = obj.matrix_world @ vert.co
            if world.z >= z_top - 0.35:
                candidates.append(Vector((world.x, world.y, world.z)))
    if len(candidates) < 8:
        return []

    lake_center = get_water_xy_center(water_objs)
    if lake_center is None:
        avg = sum(candidates, Vector()) / len(candidates)
        lake_center = Vector((avg.x, avg.y, 0.0))

    bins: dict[int, tuple[float, Vector]] = {}
    sample_count = max(samples, 32)
    for pt in candidates:
        dx = pt.x - lake_center.x
        dy = pt.y - lake_center.y
        radius = math.hypot(dx, dy)
        if radius < 1.0:
            continue
        angle = math.atan2(dy, dx)
        idx = int((angle + math.pi) / math.tau * sample_count) % sample_count
        prev = bins.get(idx)
        if prev is None or radius > prev[0]:
            bins[idx] = (radius, pt)

    if len(bins) < 8:
        return _water_shore_ring_points(water_objs, samples)

    return [bins[i][1] for i in sorted(bins)]


def _filter_shore_ring_points(
    ring: list[Vector],
    center_xy: Vector,
    min_radius: float,
) -> list[Vector]:
    """去掉离城心过近的岸线采样点（内湖岸/导入模板附近）。"""
    return [
        p for p in ring
        if math.hypot(p.x - center_xy.x, p.y - center_xy.y) >= min_radius
    ]


def _shore_tree_min_radius(city_size: Vector) -> float:
    return max(city_size.x, city_size.y) * _SHORE_TREE_MIN_CITY_CLEARANCE_RATIO


def _purge_center_tree_meshes(center_xy: Vector, min_radius: float) -> int:
    """强制删除城心附近所有树网格（含导入模板残留）。"""
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or not _is_tree_object(obj):
            continue
        loc = obj.matrix_world.translation
        if math.hypot(loc.x - center_xy.x, loc.y - center_xy.y) >= min_radius:
            continue
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
    return removed


def _tree_bark_roots(tree_objs: list[bpy.types.Object]) -> list[bpy.types.Object]:
    """LowPolyTrees 资产：每棵树以 Bark 为根，Leaves 为子级。"""
    roots: list[bpy.types.Object] = []
    seen: set[str] = set()
    for obj in tree_objs:
        if obj.type != "MESH" or not _is_tree_object(obj):
            continue
        root = obj
        while root.parent is not None and _is_tree_object(root.parent):
            root = root.parent
        if root.name in seen:
            continue
        seen.add(root.name)
        roots.append(root)
    bark_roots = [r for r in roots if "bark" in r.name.lower()]
    return bark_roots if bark_roots else roots


def _tree_rig_objects(root: bpy.types.Object) -> list[bpy.types.Object]:
    parts = [root, *[c for c in root.children_recursive if c.type == "MESH"]]
    unique: list[bpy.types.Object] = []
    seen: set[str] = set()
    for part in parts:
        if part.name in seen:
            continue
        seen.add(part.name)
        unique.append(part)
    return unique


def _duplicate_tree_rig(source_root: bpy.types.Object, *, name_tag: str) -> bpy.types.Object:
    """复制 Bark 根及其 Leaves 子网格。"""

    def _copy_part(obj: bpy.types.Object, parent: bpy.types.Object | None) -> bpy.types.Object:
        dup = obj.copy()
        if dup.data is not None:
            dup.data = dup.data.copy()
        stem = obj.name.split(".")[0]
        dup.name = f"{stem}_{name_tag}"
        bpy.context.scene.collection.objects.link(dup)
        world = obj.matrix_world.copy()
        dup.parent = parent
        dup.matrix_world = world
        for child in obj.children:
            if child.type == "MESH" and _is_tree_object(child):
                _copy_part(child, dup)
        return dup

    return _copy_part(source_root, None)


def _remove_tree_rigs(roots: Iterable[bpy.types.Object]) -> None:
    for root in roots:
        for part in reversed(_tree_rig_objects(root)):
            if part.name in bpy.data.objects:
                bpy.data.objects.remove(part, do_unlink=True)


def _remove_trees_near_center(
    tree_roots: list[bpy.types.Object],
    center_xy: Vector,
    min_radius: float,
) -> list[bpy.types.Object]:
    """删除落在城市/湖心附近的树（导入模板的默认簇）。"""
    kept: list[bpy.types.Object] = []
    for root in tree_roots:
        loc = root.matrix_world.translation
        if math.hypot(loc.x - center_xy.x, loc.y - center_xy.y) < min_radius:
            _remove_tree_rigs([root])
            continue
        kept.append(root)
    return kept


def _distribute_trees_on_shore(
    tree_objs: list[bpy.types.Object],
    water_objs: list[bpy.types.Object],
    landscape_objs: list[bpy.types.Object],
    *,
    city_xy: Vector,
    city_size: Vector,
    density_factor: float = _SHORE_TREE_DENSITY_FACTOR,
) -> list[bpy.types.Object]:
    """复制并沿岸线均匀摆放树木；模板树仅作复制源，生成后立即删除。"""
    source_roots = _tree_bark_roots(tree_objs)
    if not source_roots:
        for name in {obj.name for obj in tree_objs}:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
        return []

    min_radius = _shore_tree_min_radius(city_size)
    target_count = max(int(len(source_roots) * density_factor), len(source_roots) + 4)
    ring = _water_outer_shore_ring_points(water_objs, target_count)
    if len(ring) < 8:
        ring = _water_shore_ring_points(water_objs, target_count)
    ring = _filter_shore_ring_points(ring, city_xy, min_radius)
    if len(ring) < 4:
        _remove_tree_rigs(source_roots)
        return []

    ground_z = None
    ground_meshes = [o for o in landscape_objs if o.type == "MESH" and "Ground" in o.name]
    if ground_meshes:
        gb = _world_bounds(ground_meshes)
        if gb is not None:
            ground_z = gb[0].z

    rng = random.Random(42)
    placed_roots: list[bpy.types.Object] = []
    for idx, point in enumerate(ring):
        src = source_roots[idx % len(source_roots)]
        dup_root = _duplicate_tree_rig(src, name_tag=f"shore_{idx:03d}")
        placed_roots.append(dup_root)
        base_z = ground_z if ground_z is not None else dup_root.matrix_world.translation.z
        dup_root.location = Vector((point.x, point.y, base_z))
        dup_root.rotation_euler.z = rng.uniform(0.0, math.pi * 2.0)
        scale_jitter = rng.uniform(0.85, 1.15)
        dup_root.scale = Vector((
            dup_root.scale.x * scale_jitter,
            dup_root.scale.y * scale_jitter,
            dup_root.scale.z * scale_jitter,
        ))

    template_names = {obj.name for obj in tree_objs}
    _remove_tree_rigs(source_roots)
    for name in template_names:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)

    final_objs: list[bpy.types.Object] = []
    for root in placed_roots:
        final_objs.extend(_tree_rig_objects(root))
    return final_objs


def _scg_landscape_object_names() -> list[str]:
    names: list[str] = []
    for obj in bpy.data.objects:
        if (
            obj.name.startswith("SCG_Landscape")
            or obj.name.startswith(SCG_LAKE_TERRAIN_COLL)
            or obj.name.startswith(SCG_LAKE_TREES_COLL)
            or obj.name.startswith("SCG_Lake_")
        ):
            names.append(obj.name)
    return names


def _remove_imported_lake_collections() -> None:
    for coll in list(bpy.data.collections):
        if not (
            coll.name.startswith(SCG_LAKE_TERRAIN_COLL)
            or coll.name.startswith(SCG_LAKE_TREES_COLL)
        ):
            continue
        for obj in list(coll.all_objects):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(coll)


def _remove_objects_by_names(names: Iterable[str]) -> None:
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)


def _remove_collection_tree(coll: bpy.types.Collection) -> None:
    """递归删除集合及其全部对象（含嵌套子集合）。"""
    for child in list(coll.children):
        _remove_collection_tree(child)
    for obj in list(coll.objects):
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    if coll.name in bpy.data.collections:
        bpy.data.collections.remove(coll)


def cleanup_landscape_surround(context: Optional[bpy.types.Context] = None) -> None:
    """
    移除山水环境（含 Water/Ground/树木网格与父级 Empty）。
    清空 SCG_Ecology 集合，避免仅删 Empty 后在游标/城心残留缩小网格。
    后续接入的船只等生态对象若放入 SCG_Ecology，也会一并清除。
    """
    ctx = context or bpy.context
    _ensure_object_mode(ctx)

    base = bpy.data.objects.get("ICity Base")
    if base is not None:
        try:
            for o in ctx.view_layer.objects:
                o.select_set(False)
            base.select_set(True)
            ctx.view_layer.objects.active = base
        except (ReferenceError, RuntimeError):
            pass

    eco = bpy.data.collections.get(SCG_ECOLOGY_COLLECTION)
    if eco is not None:
        to_remove = list({obj.name for obj in eco.all_objects})
        _remove_objects_by_names(to_remove)
        _remove_collection_tree(eco)

    _remove_objects_by_names(_scg_landscape_object_names())
    _remove_imported_lake_collections()

    for coll in list(bpy.data.collections):
        if coll.name.startswith(SCG_LAKE_TERRAIN_COLL) or coll.name.startswith(SCG_LAKE_TREES_COLL):
            _remove_collection_tree(coll)

    _remove_objects_by_names(_scg_landscape_object_names())

    try:
        ctx.view_layer.update()
    except Exception:
        pass
    _flush_viewport_refresh()


def _terrain_footprint_objects(objs: list[bpy.types.Object]) -> list[bpy.types.Object]:
    """缩放/对齐以水面与地面对齐城市中心。"""
    terrain = [
        o for o in objs
        if o.type == "MESH" and ("Water" in o.name or "Ground" in o.name)
    ]
    return terrain if terrain else list(objs)


def _water_objects(objs: list[bpy.types.Object]) -> list[bpy.types.Object]:
    """以水面网格为准计算缩放与居中（Ground 比 Water 大，不能作为基准）。"""
    water = [o for o in objs if o.type == "MESH" and "Water" in o.name]
    return water if water else _terrain_footprint_objects(objs)


def _landscape_scale_for_city(city_size: Vector, water_size: Vector) -> tuple[float, float, float]:
    """按城市范围放大山水，使城市落在水面中央。"""
    margin = _WATER_CITY_MARGIN
    sx = (city_size.x * margin) / max(water_size.x, 0.01)
    sy = (city_size.y * margin) / max(water_size.y, 0.01)
    uniform = max(sx, sy)
    return uniform, uniform, uniform * 1.05


def _shift_objects_by(objects: Iterable[bpy.types.Object], offset: Vector) -> None:
    for obj in objects:
        obj.matrix_world.translation -= offset


def _shift_objects_xy(objects: Iterable[bpy.types.Object], center_xy: Vector) -> None:
    """仅 XY 居中，保留资产内 Z 相对关系（供后续对齐水面高度）。"""
    for obj in objects:
        world = obj.matrix_world.translation
        obj.matrix_world.translation = Vector((
            world.x - center_xy.x,
            world.y - center_xy.y,
            world.z,
        ))


def _align_water_surface_to_ground(
    root: bpy.types.Object,
    landscape_objs: list[bpy.types.Object],
    ground_z: float,
    context: bpy.types.Context,
) -> None:
    """将水面顶面 Z 对齐到城市道路底面（略低，避免建筑浸水）。"""
    _refresh_scene(context)
    water_bounds = _world_bounds(_water_objects(landscape_objs))
    if water_bounds is None:
        return
    _wmin, wmax = water_bounds
    root.location.z += ground_z - wmax.z
    _refresh_scene(context)


def _create_parent_empty(
    name: str,
    location: Vector,
    *,
    collection_name: str | None = None,
) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.location = location
    coll = _ensure_collection(collection_name or SCG_ECOLOGY_COLLECTION)
    coll.objects.link(empty)
    return empty


def _landscape_mesh_keywords() -> tuple[str, ...]:
    return ("Water", "Ground", "Leaves", "Bark", "Pine", "Tree", "Terrain")


def _purge_orphan_lake_meshes(managed_names: set[str]) -> int:
    """
    删除 append 后残留在游标/导入集合中的未托管湖面网格（缩小版山水）。
    """
    removed = 0
    keywords = _landscape_mesh_keywords()
    landscape_root = bpy.data.objects.get(SCG_LANDSCAPE_ROOT)
    managed_under_root: set[str] = set()
    if landscape_root is not None:
        managed_under_root.add(landscape_root.name)
        managed_under_root.update(o.name for o in landscape_root.children_recursive)

    for obj in list(bpy.data.objects):
        if obj.name in managed_names or obj.name in managed_under_root:
            continue
        if obj.type != "MESH":
            continue
        if not any(k in obj.name for k in keywords):
            continue

        in_lake_coll = any(
            c.name.startswith(SCG_LAKE_TERRAIN_COLL) or c.name.startswith(SCG_LAKE_TREES_COLL)
            for c in obj.users_collection
        )
        if in_lake_coll:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
            continue

        bounds = _world_bounds([obj])
        if bounds is None:
            continue
        span = max((bounds[1] - bounds[0]).x, (bounds[1] - bounds[0]).y)
        if span < 120.0 and any(k in obj.name for k in ("Water", "Ground", "Bark", "Leaves")):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    return removed


def _parent_objects_to(objects: Iterable[bpy.types.Object], parent: bpy.types.Object) -> None:
    for obj in objects:
        world_matrix = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_world = world_matrix


def _landscape_exists() -> bool:
    root = bpy.data.objects.get(SCG_LANDSCAPE_ROOT)
    if root is None:
        return False
    return any(
        child.name == SCG_LANDSCAPE_GROUP or child.name.startswith(SCG_LAKE_TERRAIN_COLL)
        for child in root.children
    )


def _landscape_has_orphan() -> bool:
    root = bpy.data.objects.get(SCG_LANDSCAPE_ROOT)
    return root is not None and not _landscape_exists()


def add_landscape_surround(
    context: bpy.types.Context,
) -> Tuple[bool, str]:
    """
    放置单块放大山水，城市位于水面中央。

    资产来自 lake/LowPolyTrees.blend（Terrain 水面/地面 + 岸边 Trees，树高不超过城市建筑）。
    """
    if not icity_scene_ready():
        return False, "请先 Start 并生成基础城市（需存在 ICity Base）"

    if not lake_landscape_asset_available():
        return False, f"未找到山水资产：{LAKE_BLEND}"

    _ensure_object_mode(context)

    if _landscape_exists():
        return False, "已存在山水环境（SCG_Landscape_Surround），请勿重复添加"

    if _landscape_has_orphan():
        cleanup_landscape_surround(context)

    _remove_imported_lake_collections()
    _purge_orphan_lake_meshes(set())

    city = get_city_bounds()
    if city is None:
        return False, "无法读取城市范围，请先「生成基础城市」"

    center, _half, city_size = city
    city_xy = get_city_xy_center()
    if city_xy is None:
        return False, "无法读取城市 XY 中心"
    ground_z = get_city_ground_z()
    city_span = max(city_size.x, city_size.y, 1.0)
    if city_span < 20.0:
        return False, (
            "城市范围过小（可能未生成道路/建筑）。"
            "请先点击「生成基础城市」，再添加山水"
        )

    landscape_objs, tree_objs = _build_landscape_objects(LAKE_BLEND, context)
    if not landscape_objs:
        cleanup_landscape_surround(context)
        names = _collection_names_in_blend(LAKE_BLEND)
        return False, (
            "无法从 LowPolyTrees.blend 加载 Terrain 集合。"
            f" 请确认资产路径存在；blend 内集合：{sorted(names)}"
        )

    all_objs = landscape_objs + tree_objs

    footprint = _water_objects(landscape_objs)
    water_bounds = _world_bounds(footprint)
    if water_bounds is None:
        cleanup_landscape_surround(context)
        return False, "山水资产无有效水面/地面网格"

    wmin, wmax = water_bounds
    water_size = wmax - wmin
    water_center_xy = (wmin + wmax) * 0.5
    _shift_objects_xy(landscape_objs, water_center_xy)
    # 树木模板不参与居中/缩放，仅作复制源，生成后删除

    sx, sy, sz = _landscape_scale_for_city(city_size, water_size)

    _ensure_collection(SCG_ECOLOGY_COLLECTION)
    eco_coll = bpy.data.collections[SCG_ECOLOGY_COLLECTION]
    eco_coll.hide_viewport = False
    eco_coll.hide_render = False

    root_loc = Vector((city_xy.x, city_xy.y, ground_z))
    root = _create_parent_empty(SCG_LANDSCAPE_ROOT, root_loc)
    group = _create_parent_empty(SCG_LANDSCAPE_GROUP, root_loc)
    group.parent = root
    group.location = Vector((0.0, 0.0, 0.0))
    group.scale = (sx, sy, sz)

    # 仅地形/水面继承放大缩放；树木单独挂到 root，避免被整体放大
    _parent_objects_to(landscape_objs, group)
    _refresh_scene(context)
    _align_water_surface_to_ground(root, landscape_objs, ground_z, context)

    building_h = _measure_max_building_height(ground_z)
    target_tree_h = _shore_tree_target_height(ground_z)
    water_meshes = _water_objects(landscape_objs)
    shore_min_r = _shore_tree_min_radius(city_size)
    expanded_trees = _distribute_trees_on_shore(
        tree_objs,
        water_meshes,
        landscape_objs,
        city_xy=city_xy,
        city_size=city_size,
    )
    expanded_roots = _tree_bark_roots(expanded_trees)
    expanded_roots = _remove_trees_near_center(expanded_roots, city_xy, shore_min_r)
    expanded_trees = [part for root in expanded_roots for part in _tree_rig_objects(root)]
    _scale_shore_trees_to_height(expanded_trees, target_tree_h)
    _cap_trees_world_height(expanded_trees, building_h)
    _parent_objects_to(expanded_trees, root)
    center_trees_removed = _purge_center_tree_meshes(city_xy, shore_min_r)

    all_objs = landscape_objs + expanded_trees

    _move_objects_to_collection(all_objs + [group, root], SCG_ECOLOGY_COLLECTION)
    _remove_imported_lake_collections()
    managed_names = {o.name for o in all_objs + [group, root]}
    orphans_removed = _purge_orphan_lake_meshes(managed_names)
    tex_fixed = _relink_textures_in_objects(all_objs, LAKE_TEXTURE_SEARCH_DIRS)

    _flush_viewport_refresh()

    scaled_water = Vector((water_size.x * sx, water_size.y * sy, water_size.z * sz))
    return True, (
        f"已添加中央山水：地形 {len(landscape_objs)} + 岸边树 {len(expanded_roots)}；"
        f"树高≈{target_tree_h:.1f}m（最高楼≈{building_h:.1f}m，树不超过楼高）；"
        f"城市≈{city_size.x:.0f}×{city_size.y:.0f}m，"
        f"水面≈{scaled_water.x:.0f}×{scaled_water.y:.0f}m，"
        f"水面高度≈{ground_z:.2f}m（对齐道路底）；"
        f"湖心≈({root.location.x:.0f}, {root.location.y:.0f})；"
        f"清理残留网格 {orphans_removed} 处，城心树 {center_trees_removed} 处；"
        f"重连贴图 {tex_fixed} 处。Outliner → SCG_Ecology 查看"
    )


# 兼容主文档命名（河流+山体合一为山水）
def add_river(context: bpy.types.Context) -> Tuple[bool, str]:
    return add_landscape_surround(context)


def add_mountain(context: bpy.types.Context) -> Tuple[bool, str]:
    return add_landscape_surround(context)
