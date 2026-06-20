"""
路径提取与路径关键帧动画（阶段三 C）。
"""

from __future__ import annotations

import math
from typing import Optional, TypedDict

import bmesh
import bpy
from mathutils import Vector

from .scene_enhance import (
    get_city_bounds,
    get_city_xy_center,
    get_landscape_xy_center,
    get_road_surface_z,
    get_scg_water_objects,
    get_water_surface_z,
    get_water_xy_center,
    min_boat_orbit_radius,
    point_xy_clear_of_city,
    sample_water_outer_shore_ring,
    water_surface_z_at_xy,
)

SCG_PATH_PREFIX = "SCG_Path_"
SCG_PATH_COLLECTION = "SCG_Paths"
SCG_PATH_BOAT_LOOP = "SCG_Path_Boat_Loop"
# 船只环线：湖心到外岸的比例（越小越靠开阔水面、远离岸边）
_BOAT_OPEN_WATER_RATIO = 0.38
_BOAT_CITY_CLEARANCE_M = 28.0
_BOAT_SHORE_MARGIN_M = 18.0
_MIN_ROAD_EDGE_LEN = 20.0
_POINT_MATCH_EPS = 0.5

# 默认道路横断面（米）：里层人行道 | 双向机动车道 | 外层人行道
DEFAULT_LANE_WIDTH_M = 3.5
DEFAULT_SIDEWALK_WIDTH_M = 2.5
# 兼容旧接口
DEFAULT_CAR_LANE_OFFSET_M = DEFAULT_LANE_WIDTH_M * 0.5
DEFAULT_SIDEWALK_OFFSET_M = DEFAULT_LANE_WIDTH_M + DEFAULT_SIDEWALK_WIDTH_M * 0.5


class RoadCrossSection(TypedDict):
    lane_width: float
    sidewalk_width: float
    half_lane: float
    sidewalk_center: float


def _road_cross_section_from_mesh() -> RoadCrossSection | None:
    base_obj = bpy.data.objects.get("ICity Base")
    if base_obj is None or base_obj.data is None:
        return None

    mesh = base_obj.data
    lane_w = DEFAULT_LANE_WIDTH_M
    sidewalk_w = DEFAULT_SIDEWALK_WIDTH_M
    lane_attr = mesh.attributes.get("Road lanes width")
    walk_attr = mesh.attributes.get("side walk offset")
    if lane_attr is not None and len(lane_attr.data):
        values = [item.value for item in lane_attr.data if item.value > 0.01]
        if values:
            lane_w = max(values)
    if walk_attr is not None and len(walk_attr.data):
        values = [item.value for item in walk_attr.data if item.value > 0.01]
        if values:
            # ICity 属性 side walk offset = 人行道宽度（米）
            sidewalk_w = max(values)

    half_lane = lane_w * 0.5
    # 中心线 → 车道外缘 half_lane，再过半条人行道
    sidewalk_center = half_lane + sidewalk_w * 0.5
    return {
        "lane_width": lane_w,
        "sidewalk_width": sidewalk_w,
        "half_lane": half_lane,
        "sidewalk_center": sidewalk_center,
    }


def get_road_cross_section() -> RoadCrossSection:
    section = _road_cross_section_from_mesh()
    if section is not None:
        return section
    half_lane = DEFAULT_LANE_WIDTH_M * 0.5
    sidewalk_center = half_lane + DEFAULT_SIDEWALK_WIDTH_M * 0.5
    return {
        "lane_width": DEFAULT_LANE_WIDTH_M,
        "sidewalk_width": DEFAULT_SIDEWALK_WIDTH_M,
        "half_lane": half_lane,
        "sidewalk_center": sidewalk_center,
    }


def get_road_lateral_offsets() -> tuple[float, float]:
    """
    读取车道 / 人行道横向偏移（相对道路中心线，米）。
    返回 (half_lane_width, sidewalk_center_offset)。
    """
    section = get_road_cross_section()
    return section["half_lane"], section["sidewalk_center"]


def get_animation_frame_range(scene: bpy.types.Scene) -> tuple[int, int]:
    """读取场景动画帧范围（scg_animation_frame_end 或默认 1–120）。"""
    end = int(getattr(scene, "scg_animation_frame_end", 120))
    return 1, max(end, 2)


def _ensure_collection(name: str, parent: Optional[bpy.types.Collection] = None) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        if parent is not None:
            parent.children.link(coll)
        else:
            bpy.context.scene.collection.children.link(coll)
    return coll


def _street_edge_segments(base_obj: bpy.types.Object) -> list[tuple[Vector, Vector]]:
    """从 ICity Base 提取道路边（世界坐标，含环路全部边）。"""
    mesh = base_obj.data
    if mesh is None:
        return []

    attr_road = mesh.attributes.get("Road del")
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    matrix = base_obj.matrix_world
    segments: list[tuple[Vector, Vector]] = []

    for idx, edge in enumerate(bm.edges):
        is_road = True
        if attr_road is not None and idx < len(attr_road.data):
            is_road = not attr_road.data[idx].value
        if not is_road:
            continue

        v0 = matrix @ edge.verts[0].co
        v1 = matrix @ edge.verts[1].co
        if (v0 - v1).length >= _MIN_ROAD_EDGE_LEN:
            segments.append((v0, v1))

    bm.free()
    return segments


def _points_match(a: Vector, b: Vector) -> bool:
    return (a - b).length <= _POINT_MATCH_EPS


def _order_segments_into_loop(
    segments: list[tuple[Vector, Vector]],
) -> list[tuple[Vector, Vector]]:
    """将道路边排序为闭合环路（顺时针）。"""
    if not segments:
        return []

    remaining = list(segments)
    ordered: list[tuple[Vector, Vector]] = [remaining.pop(0)]
    current_end = ordered[0][1]

    while remaining:
        matched = False
        for idx, (start, end) in enumerate(remaining):
            if _points_match(start, current_end):
                ordered.append((start, end))
                current_end = end
                remaining.pop(idx)
                matched = True
                break
            if _points_match(end, current_end):
                ordered.append((end, start))
                current_end = start
                remaining.pop(idx)
                matched = True
                break
        if not matched:
            break

    return ordered


def _loop_center(segments: list[tuple[Vector, Vector]]) -> Vector:
    points: list[Vector] = []
    for start, end in segments:
        points.append(start)
        points.append(end)
    if not points:
        return Vector((0.0, 0.0, 0.0))
    center = Vector((0.0, 0.0, 0.0))
    for point in points:
        center += point
    center /= len(points)
    center.z = points[0].z
    return center


def extract_street_loop() -> list[tuple[Vector, Vector]]:
    """提取有序闭合道路环路（机动车道中心线）。"""
    base_obj = bpy.data.objects.get("ICity Base")
    if base_obj is None:
        return []

    segments = _street_edge_segments(base_obj)
    segments.sort(key=lambda seg: -(seg[0] - seg[1]).length)
    ordered = _order_segments_into_loop(segments)
    if len(ordered) < 2:
        return ordered

    if not _points_match(ordered[-1][1], ordered[0][0]):
        # 无法闭合时仍返回最长边，供回退使用
        return ordered[: max(len(ordered), 1)]
    return ordered


def extract_street_segments(*, max_paths: int = 4) -> list[tuple[Vector, Vector]]:
    loop = extract_street_loop()
    if loop:
        return loop[:max_paths]
    base_obj = bpy.data.objects.get("ICity Base")
    if base_obj is None:
        return []
    segments = _street_edge_segments(base_obj)
    segments.sort(key=lambda seg: -(seg[0] - seg[1]).length)
    return segments[:max_paths]


def _path_right_vector(start: Vector, end: Vector) -> Vector:
    """路径前进方向的右侧单位向量（Z 朝上）。"""
    forward = end - start
    if forward.length < 1e-6:
        return Vector((1.0, 0.0, 0.0))
    forward.normalize()
    right = forward.cross(Vector((0.0, 0.0, 1.0)))
    if right.length < 1e-6:
        return Vector((1.0, 0.0, 0.0))
    right.normalize()
    return right


def _right_hand_lateral_sign(
    start: Vector,
    end: Vector,
    loop_center: Vector,
    *,
    inward: bool,
) -> float:
    """
    右行规则下的横向偏移符号。
    inward=True：靠环路内侧（机动车道）；False：靠外侧（人行道）。
    """
    right = _path_right_vector(start, end)
    mid = (start + end) * 0.5
    toward_center = loop_center - mid
    toward_center.z = 0.0
    if toward_center.length < 1e-6:
        return 1.0
    toward_center.normalize()
    sign = 1.0 if right.dot(toward_center) >= 0.0 else -1.0
    return sign if inward else -sign


def _curve_from_points(name: str, points: list[Vector], *, cyclic: bool = False) -> bpy.types.Object:
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 24
    if not points:
        spline = curve_data.splines.new("POLY")
        obj = bpy.data.objects.new(name, curve_data)
        bpy.context.scene.collection.objects.link(obj)
        return obj
    spline = curve_data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for idx, point in enumerate(points):
        spline.points[idx].co = (point.x, point.y, point.z, 1.0)
    spline.use_cyclic_u = cyclic

    obj = bpy.data.objects.new(name, curve_data)
    obj.location = (0.0, 0.0, 0.0)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _loop_vertices(loop_segments: list[tuple[Vector, Vector]]) -> list[Vector]:
    if not loop_segments:
        return []
    vertices = [loop_segments[0][0]]
    for _start, end in loop_segments:
        vertices.append(end)
    if len(vertices) > 1 and _points_match(vertices[0], vertices[-1]):
        vertices.pop()
    return vertices


def _inward_vector(point: Vector, loop_center: Vector) -> Vector:
    """环路内侧（指向城市中心）单位向量。"""
    inward = loop_center - point
    inward.z = 0.0
    if inward.length < 1e-6:
        return Vector((0.0, 0.0, 0.0))
    inward.normalize()
    return inward


def _loop_vertices_from_segments(loop_segments: list[tuple[Vector, Vector]]) -> list[Vector]:
    return _loop_vertices(loop_segments)


def _build_segment_offset_loop(
    loop_segments: list[tuple[Vector, Vector]],
    *,
    loop_center: Vector,
    surface_z: float,
    offset_fn,
    reverse_order: bool = False,
) -> list[Vector]:
    """
    沿每段道路中心线做法向/径向偏移，避免角点「切圆心」导致侵入人行道。
    offset_fn(start, end, t) -> Vector 为 t∈{0,0.5,1} 处的世界 XY 偏移点。
    """
    if not loop_segments:
        return []

    segments = list(reversed(loop_segments)) if reverse_order else list(loop_segments)
    points: list[Vector] = []
    for start, end in segments:
        for t in (0.0, 0.5):
            pt = offset_fn(start, end, t)
            points.append(Vector((pt.x, pt.y, surface_z)))

    if reverse_order and points:
        points.reverse()
    return points


def _corner_blend_loop_points(points: list[Vector]) -> list[Vector]:
    """闭合环路角点平滑：相邻段端点取平均，减少转弯处侧滑。"""
    if len(points) < 4:
        return points
    count = len(points)
    blended: list[Vector] = []
    for idx in range(count):
        prev_pt = points[(idx - 1) % count]
        cur_pt = points[idx]
        nxt_pt = points[(idx + 1) % count]
        if idx % 2 == 0:
            blended.append(cur_pt)
        else:
            blended.append((prev_pt + cur_pt + nxt_pt) / 3.0)
    return blended


def create_lane_loop_curve(
    name: str,
    loop_segments: list[tuple[Vector, Vector]],
    *,
    lateral_offset: float,
    surface_z: float,
    loop_center: Vector,
    lane_band: float = 1.0,
    reverse: bool = False,
) -> bpy.types.Object:
    """
    沿闭合环路生成机动车道曲线（右行规则）。
    lane_band=1：顺时针车道（中心线 + 右侧 half_lane）；
    lane_band=-1：逆时针车道（中心线 - 右侧 half_lane，点序反向）。
    """
    half_lane = abs(lateral_offset)
    clockwise_lane = lane_band >= 0.0
    lane_sign = 1.0 if clockwise_lane else -1.0

    def offset_fn(start: Vector, end: Vector, t: float) -> Vector:
        base = start + (end - start) * t
        right = _path_right_vector(start, end)
        return base + right * (half_lane * lane_sign)

    offset_pts = _build_segment_offset_loop(
        loop_segments,
        loop_center=loop_center,
        surface_z=surface_z,
        offset_fn=offset_fn,
        reverse_order=not clockwise_lane,
    )
    offset_pts = _corner_blend_loop_points(offset_pts)
    return _curve_from_points(name, offset_pts, cyclic=True)


def create_sidewalk_loop_curve(
    name: str,
    loop_segments: list[tuple[Vector, Vector]],
    *,
    lateral_offset: float,
    surface_z: float,
    loop_center: Vector,
    outer: bool = True,
    reverse: bool = False,
) -> bpy.types.Object:
    """人行道环路：outer=True 外层（靠建筑），False 里层（靠城市中心）。"""
    sidewalk_center = abs(lateral_offset)

    def offset_fn(start: Vector, end: Vector, t: float) -> Vector:
        p0, p1 = (end, start) if reverse else (start, end)
        base = p0 + (p1 - p0) * t
        right = _path_right_vector(p0, p1)
        # 垂直于路段、相对环路中心区分里/外，避免径向偏移把行人拉到机动车道
        sign = _right_hand_lateral_sign(p0, p1, loop_center, inward=not outer)
        return base + right * (sidewalk_center * sign)

    offset_pts = _build_segment_offset_loop(
        loop_segments,
        loop_center=loop_center,
        surface_z=surface_z,
        offset_fn=offset_fn,
        reverse_order=reverse,
    )
    offset_pts = _corner_blend_loop_points(offset_pts)
    if not outer:
        offset_pts.reverse()
    return _curve_from_points(name, offset_pts, cyclic=True)


# --- 手动路径（用户绘制贝塞尔曲线，见 docs/manual_path_curves.md）---

MANUAL_PATH_CAR_CW = "SCG_Manual_Car_CW"
MANUAL_PATH_CAR_CCW = "SCG_Manual_Car_CCW"
MANUAL_PATH_PED_INNER = "SCG_Manual_Ped_Inner"
MANUAL_PATH_PED_OUTER = "SCG_Manual_Ped_Outer"
MANUAL_PATH_BOAT = "SCG_Manual_Boat"

_MANUAL_PATH_NAMES = (
    MANUAL_PATH_CAR_CW,
    MANUAL_PATH_CAR_CCW,
    MANUAL_PATH_PED_INNER,
    MANUAL_PATH_PED_OUTER,
    MANUAL_PATH_BOAT,
)

_MANUAL_CAR_PATH_NAMES = (MANUAL_PATH_CAR_CW, MANUAL_PATH_CAR_CCW)
_MANUAL_PED_PATH_NAMES = (MANUAL_PATH_PED_INNER, MANUAL_PATH_PED_OUTER)

SCG_MANUAL_PATHS_COLLECTION = "SCG_ManualPaths"


def _is_manual_path_curve(curve_obj: bpy.types.Object) -> bool:
    return curve_obj.name in _MANUAL_PATH_NAMES or curve_obj.name.startswith("SCG_Manual_")


def random_spaced_path_offsets(
    count: int,
    *,
    min_gap: float = 0.10,
    seed: int = 42,
) -> list[float]:
    """在闭合曲线 [0,1) 上生成随机、互不重叠的起点参数。"""
    import random

    if count <= 0:
        return []
    if count == 1:
        rng = random.Random(seed)
        return [rng.random()]

    min_gap = max(min_gap, 0.75 / max(count, 1))
    rng = random.Random(seed)
    for _ in range(3000):
        offsets = sorted(rng.random() for _ in range(count))
        ok = True
        for i in range(count):
            a = offsets[i]
            b = offsets[(i + 1) % count]
            gap = (b - a) if i < count - 1 else (1.0 - a + b)
            if gap < min_gap:
                ok = False
                break
        if ok:
            return offsets

    spacing = 1.0 / count
    return [((i + 0.5) * spacing) % 1.0 for i in range(count)]


def find_manual_path(name: str) -> bpy.types.Object | None:
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type == "CURVE":
        return obj
    return None


def manual_paths_active() -> bool:
    return any(find_manual_path(n) is not None for n in _MANUAL_PATH_NAMES)


def remove_manual_paths_from_scene() -> int:
    """移除场景中已有手动画路径（加载库前调用）。"""
    removed = 0
    for name in _MANUAL_PATH_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    return removed


def append_manual_paths_from_library(
    context: bpy.types.Context,
    *,
    replace_existing: bool = True,
) -> tuple[bool, str]:
    """
    从 assets/manual_paths/manual_paths.blend 追加 4 条命名曲线到当前场景。
    """
    from .assets_manager import MANUAL_PATHS_BLEND, manual_paths_library_available

    if not manual_paths_library_available():
        return False, (
            "未找到路径库 manual_paths.blend。"
            "请在大纲中命名好曲线后，点击「保存曲线到路径库」。"
        )

    if replace_existing:
        remove_manual_paths_from_scene()

    try:
        with bpy.data.libraries.load(MANUAL_PATHS_BLEND, link=False) as (data_from, data_to):
            to_load = [n for n in _MANUAL_PATH_NAMES if n in data_from.objects]
            if not to_load:
                return False, "路径库中无 SCG_Manual_* 曲线，请先「保存曲线到路径库」。"
            data_to.objects = to_load
    except OSError as exc:
        return False, f"无法读取路径库：{exc}"

    coll = _ensure_collection(SCG_MANUAL_PATHS_COLLECTION)
    loaded: list[bpy.types.Object] = []
    for name in _MANUAL_PATH_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        for user_coll in list(obj.users_collection):
            user_coll.objects.unlink(obj)
        coll.objects.link(obj)
        loaded.append(obj)

    if not loaded:
        return False, "路径库加载失败：未找到有效曲线对象。"

    coll.hide_viewport = False
    coll.hide_render = True
    _ = context
    return True, f"已从路径库加载 {len(loaded)} 条曲线 → 集合 {SCG_MANUAL_PATHS_COLLECTION}"


def ensure_manual_car_paths_in_scene(context: bpy.types.Context) -> bool:
    """
    若场景中无车道曲线，则从 manual_paths.blend 自动追加 CW/CCW（不删除已有对象）。
    """
    if find_manual_path(MANUAL_PATH_CAR_CW) and find_manual_path(MANUAL_PATH_CAR_CCW):
        return True

    from .assets_manager import MANUAL_PATHS_BLEND, manual_paths_library_available

    if not manual_paths_library_available():
        return False

    try:
        with bpy.data.libraries.load(MANUAL_PATHS_BLEND, link=False) as (data_from, data_to):
            to_load = [n for n in _MANUAL_CAR_PATH_NAMES if n in data_from.objects]
            if len(to_load) < 2:
                return False
            data_to.objects = to_load
    except OSError:
        return False

    coll = _ensure_collection(SCG_MANUAL_PATHS_COLLECTION)
    for name in _MANUAL_CAR_PATH_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        for user_coll in list(obj.users_collection):
            user_coll.objects.unlink(obj)
        coll.objects.link(obj)

    coll.hide_viewport = False
    coll.hide_render = True
    _ = context
    return find_manual_path(MANUAL_PATH_CAR_CW) is not None and find_manual_path(MANUAL_PATH_CAR_CCW) is not None


def ensure_manual_boat_path_in_scene(context: bpy.types.Context) -> bool:
    """若场景中存在或路径库含 SCG_Manual_Boat，则自动加载手动画船只曲线。"""
    if find_manual_path(MANUAL_PATH_BOAT):
        return True

    from .assets_manager import MANUAL_PATHS_BLEND, manual_paths_library_available

    if not manual_paths_library_available():
        return False

    try:
        with bpy.data.libraries.load(MANUAL_PATHS_BLEND, link=False) as (data_from, data_to):
            if MANUAL_PATH_BOAT not in data_from.objects:
                return False
            data_to.objects = [MANUAL_PATH_BOAT]
    except OSError:
        return False

    coll = _ensure_collection(SCG_MANUAL_PATHS_COLLECTION)
    obj = bpy.data.objects.get(MANUAL_PATH_BOAT)
    if obj is None:
        return False
    for user_coll in list(obj.users_collection):
        user_coll.objects.unlink(obj)
    coll.objects.link(obj)
    coll.hide_viewport = False
    coll.hide_render = True
    _ = context
    return True


def create_pedestrian_paths_from_lane_curves(
    cw_curve: bpy.types.Object,
    ccw_curve: bpy.types.Object,
    *,
    half_lane: float,
    sidewalk_width: float,
    surface_z: float,
    loop_center: Vector,
) -> tuple[bpy.types.Object, bpy.types.Object]:
    """
    沿两条机动车道曲线向心/离心偏移生成里/外人行道中心线，避免行人进入车道。
    offset = 半车道宽 + 半人行道宽（从车道中心到人行道中心）。
    """
    lane_to_sidewalk = half_lane + sidewalk_width * 0.5
    cw_pts = _curve_world_points(cw_curve, samples=160)
    ccw_pts = _curve_world_points(ccw_curve, samples=160)
    if len(cw_pts) < 4 or len(ccw_pts) < 4:
        raise ValueError("机动车道曲线采样点不足")

    center = loop_center.copy()
    if center.length < 1e-3:
        center = sum(cw_pts, Vector()) / len(cw_pts)
        center.z = surface_z

    def _offset_ring(
        points: list[Vector],
        *,
        inward: bool,
    ) -> list[Vector]:
        ring: list[Vector] = []
        count = len(points)
        for idx, pt in enumerate(points):
            nxt = points[(idx + 1) % count]
            right = _path_right_vector(pt, nxt)
            sign = _right_hand_lateral_sign(pt, nxt, center, inward=inward)
            off = right * (lane_to_sidewalk * sign)
            ring.append(Vector((pt.x + off.x, pt.y + off.y, surface_z)))
        return ring

    # 里层：相对环路中心内侧；外层：外侧（靠建筑）
    inner_pts = _offset_ring(cw_pts, inward=True)
    outer_pts = _offset_ring(ccw_pts, inward=False)

    inner_curve = _curve_from_points("SCG_Path_Ped_Inner", inner_pts, cyclic=True)
    outer_curve = _curve_from_points("SCG_Path_Ped_Outer", outer_pts, cyclic=True)
    return inner_curve, outer_curve


def create_boat_water_loop_curve(
    *,
    name: str = SCG_PATH_BOAT_LOOP,
    samples: int = 128,
    city_clearance_m: float = _BOAT_CITY_CLEARANCE_M,
    open_water_ratio: float = _BOAT_OPEN_WATER_RATIO,
) -> bpy.types.Object | None:
    """
    在城市外围、远离岸边的开阔水面生成闭合船行路径。
    open_water_ratio：岸线到城市之间靠岸一侧的比例（越小越远离岸边）。
    """
    water_objs = get_scg_water_objects()
    if not water_objs:
        return None

    surface_z = get_water_surface_z()
    if surface_z is None:
        return None

    ring = sample_water_outer_shore_ring(water_objs, samples)
    if len(ring) < 8:
        return None

    lake_xy = get_water_xy_center(water_objs)
    if lake_xy is None:
        lake_xy = get_landscape_xy_center()
    if lake_xy is None:
        lake_xy = get_city_xy_center()
    if lake_xy is None:
        center = sum(ring, Vector()) / len(ring)
        lake_xy = Vector((center.x, center.y, 0.0))

    city_xy = get_city_xy_center() or lake_xy
    min_radius = min_boat_orbit_radius(city_clearance_m)

    boat_pts: list[Vector] = []
    for pt in ring:
        delta = Vector((pt.x - lake_xy.x, pt.y - lake_xy.y, 0.0))
        shore_dist = delta.length
        if shore_dist < 12.0:
            continue
        direction = delta / shore_dist
        boat_dist = shore_dist * open_water_ratio
        boat_dist = min(boat_dist, shore_dist - _BOAT_SHORE_MARGIN_M)
        boat_dist = max(boat_dist, shore_dist * 0.22)
        boat_xy = lake_xy + direction * boat_dist
        if _xy_radius(Vector((boat_xy.x, boat_xy.y, 0.0)), city_xy) < min_radius:
            city_delta = Vector((boat_xy.x - city_xy.x, boat_xy.y - city_xy.y, 0.0))
            if city_delta.length > 1e-3:
                boat_xy = city_xy + city_delta.normalized() * min_radius
            else:
                boat_xy = city_xy + direction * min_radius
        if not point_xy_clear_of_city(boat_xy.x, boat_xy.y, city_clearance_m * 0.35):
            continue
        z = water_surface_z_at_xy(boat_xy.x, boat_xy.y, water_objs, surface_z)
        boat_pts.append(Vector((boat_xy.x, boat_xy.y, z)))

    if len(boat_pts) < 8:
        return None

    boat_pts = _corner_blend_loop_points(boat_pts)
    curve = _curve_from_points(name, boat_pts, cyclic=True)
    link_path_to_collection(curve)
    return curve


def _collect_manual_path_objects() -> list[bpy.types.Object]:
    """收集场景中已正确命名的手动画路径曲线。"""
    found: list[bpy.types.Object] = []
    for name in _MANUAL_PATH_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.type == "CURVE":
            found.append(obj)
    return found


def _find_manual_path_typos() -> list[str]:
    """常见命名错误（如 manual 小写）。"""
    typos: list[str] = []
    for obj in bpy.data.objects:
        if obj.type != "CURVE":
            continue
        lower = obj.name.lower()
        if lower.startswith("scg_manual_") and obj.name not in _MANUAL_PATH_NAMES:
            typos.append(obj.name)
    return typos


def export_manual_paths_to_library(context: bpy.types.Context) -> tuple[bool, str]:
    """
    将 SCG_Manual_* 曲线写入 assets/manual_paths/manual_paths.blend。

    合并策略：场景中已命名的曲线优先更新；路径库中其余曲线保留（不会只存船只而删掉车辆曲线）。
    """
    import os

    from .assets_manager import MANUAL_PATHS_BLEND, MANUAL_PATHS_DIR

    scene_paths = _collect_manual_path_objects()
    if not scene_paths:
        typos = _find_manual_path_typos()
        hint = ""
        if typos:
            hint = f" 发现疑似拼写错误：{', '.join(typos)}（Manual 的 M 须大写）"
        if not os.path.isfile(MANUAL_PATHS_BLEND):
            return False, f"场景中未找到 SCG_Manual_* 曲线。{hint}"
        if not hint:
            hint = " 场景中至少需要一条 SCG_Manual_* 曲线才能更新路径库。"

    scene_by_name = {obj.name: obj for obj in scene_paths}
    library_imported: list[bpy.types.Object] = []
    library_by_name: dict[str, bpy.types.Object] = {}

    if os.path.isfile(MANUAL_PATHS_BLEND):
        before = set(bpy.data.objects)
        try:
            with bpy.data.libraries.load(MANUAL_PATHS_BLEND, link=False) as (data_from, data_to):
                to_load = [
                    name for name in _MANUAL_PATH_NAMES
                    if name in data_from.objects and name not in scene_by_name
                ]
                data_to.objects = to_load
        except OSError as exc:
            return False, f"无法读取现有路径库：{exc}"

        for obj in bpy.data.objects:
            if obj in before or obj.type != "CURVE":
                continue
            if obj.name in _MANUAL_PATH_NAMES:
                library_by_name[obj.name] = obj
                library_imported.append(obj)

    export_objs: list[bpy.types.Object] = []
    updated_from_scene: list[str] = []
    kept_from_library: list[str] = []
    for name in _MANUAL_PATH_NAMES:
        if name in scene_by_name:
            export_objs.append(scene_by_name[name])
            updated_from_scene.append(name)
        elif name in library_by_name:
            export_objs.append(library_by_name[name])
            kept_from_library.append(name)

    if not export_objs:
        for obj in library_imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        typos = _find_manual_path_typos()
        hint = ""
        if typos:
            hint = f" 发现疑似拼写错误：{', '.join(typos)}（Manual 的 M 须大写）"
        return False, f"场景中未找到 SCG_Manual_* 曲线，且路径库为空。{hint}"

    os.makedirs(MANUAL_PATHS_DIR, exist_ok=True)

    export_count = len(export_objs)
    export_names = ", ".join(obj.name for obj in export_objs)
    imported_names = [obj.name for obj in library_imported]

    datablocks: set[bpy.types.ID] = set()
    for obj in export_objs:
        datablocks.add(obj)
        if obj.data is not None:
            datablocks.add(obj.data)

    try:
        bpy.data.libraries.write(
            MANUAL_PATHS_BLEND,
            datablocks,
            fake_user=True,
            compress=False,
        )
    except (OSError, RuntimeError, TypeError) as exc:
        for name in imported_names:
            temp = bpy.data.objects.get(name)
            if temp is not None and temp.name not in scene_by_name:
                bpy.data.objects.remove(temp, do_unlink=True)
        return False, f"导出路径库失败：{exc}"

    for name in imported_names:
        temp = bpy.data.objects.get(name)
        if temp is not None and temp.name not in scene_by_name:
            bpy.data.objects.remove(temp, do_unlink=True)

    size_mb = os.path.getsize(MANUAL_PATHS_BLEND) / (1024 * 1024)
    msg = f"已保存 {export_count} 条 → manual_paths.blend（{size_mb:.2f} MB）：{export_names}"
    if updated_from_scene:
        msg += f"；本次更新：{', '.join(updated_from_scene)}"
    if kept_from_library:
        msg += f"；保留库内：{', '.join(kept_from_library)}"
    missing = [n for n in _MANUAL_PATH_NAMES if n not in scene_by_name and n not in library_by_name]
    if missing:
        msg += f"；尚未画：{', '.join(missing)}"
    _ = context
    return True, msg


def _resample_polyline_uniform(points: list[Vector], count: int) -> list[Vector]:
    """按弧长均匀重采样闭合折线。"""
    if len(points) < 2 or count < 2:
        return points

    ring = list(points)
    if (ring[0] - ring[-1]).length > 1e-4:
        ring.append(ring[0].copy())

    segs: list[tuple[float, float, Vector, Vector]] = []
    total = 0.0
    for idx in range(len(ring) - 1):
        p0, p1 = ring[idx], ring[idx + 1]
        seg_len = (p1 - p0).length
        if seg_len < 1e-6:
            continue
        segs.append((total, total + seg_len, p0, p1))
        total += seg_len

    if total < 1e-6 or not segs:
        return points

    resampled: list[Vector] = []
    for i in range(count):
        dist = (i / count) * total
        for start_d, end_d, p0, p1 in segs:
            if dist <= end_d + 1e-6:
                seg_len = end_d - start_d
                alpha = (dist - start_d) / seg_len if seg_len > 1e-6 else 0.0
                alpha = max(0.0, min(1.0, alpha))
                resampled.append(p0.lerp(p1, alpha))
                break
        else:
            resampled.append(segs[-1][3].copy())
    return resampled


def _dedupe_polyline_points(points: list[Vector], min_dist: float = 0.08) -> list[Vector]:
    if not points:
        return []
    cleaned = [points[0].copy()]
    for pt in points[1:]:
        if (pt - cleaned[-1]).length >= min_dist:
            cleaned.append(pt.copy())
    if len(cleaned) > 2 and (cleaned[0] - cleaned[-1]).length < min_dist:
        cleaned.pop()
    return cleaned


def _close_polyline_points(points: list[Vector]) -> list[Vector]:
    if len(points) < 2:
        return points
    closed = [p.copy() for p in points]
    if (closed[0] - closed[-1]).length > 0.05:
        closed.append(closed[0].copy())
    else:
        closed[-1] = closed[0].copy()
    return closed


def _path_xy_center(points: list[Vector]) -> Vector:
    city = get_city_xy_center()
    if city is not None:
        return Vector((city.x, city.y, 0.0))
    if not points:
        return Vector((0.0, 0.0, 0.0))
    center = sum(points, Vector()) / len(points)
    return Vector((center.x, center.y, 0.0))


def _xy_radius(point: Vector, center: Vector) -> float:
    return Vector((point.x - center.x, point.y - center.y, 0.0)).length


def _prune_path_centroid_spikes(
    points: list[Vector],
    center_xy: Vector,
    *,
    min_radius_ratio: float = 0.38,
) -> list[Vector]:
    """去掉折线中深入环心、远离车道的一小撮采样点（手动画曲线常见）。"""
    if len(points) < 8:
        return points
    radii = [_xy_radius(p, center_xy) for p in points]
    max_r = max(radii)
    if max_r < 1e-3:
        return points
    threshold = max_r * min_radius_ratio
    kept = [p for p, r in zip(points, radii) if r >= threshold]
    if len(kept) < max(8, len(points) * 3 // 4):
        return points
    return _dedupe_polyline_points(kept)


def _rotate_closed_polyline(points: list[Vector], start_index: int) -> list[Vector]:
    if not points or start_index <= 0:
        return points
    idx = start_index % len(points)
    return points[idx:] + points[:idx]


def _phase_path_start_on_perimeter(points: list[Vector], center_xy: Vector) -> list[Vector]:
    """让 t=0 落在离城市中心最远的路段，避免首辆车出现在环心。"""
    if len(points) < 4:
        return points
    best_i = max(
        range(len(points)),
        key=lambda i: _xy_radius(points[i], center_xy),
    )
    return _rotate_closed_polyline(points, best_i)


def _cubic_bezier_point(p0: Vector, p1: Vector, p2: Vector, p3: Vector, t: float) -> Vector:
    u = 1.0 - t
    return (
        (u ** 3) * p0
        + 3.0 * (u ** 2) * t * p1
        + 3.0 * u * (t ** 2) * p2
        + (t ** 3) * p3
    )


def _cubic_bezier_tangent(p0: Vector, p1: Vector, p2: Vector, p3: Vector, t: float) -> Vector:
    u = 1.0 - t
    return (
        3.0 * (u ** 2) * (p1 - p0)
        + 6.0 * u * t * (p2 - p1)
        + 3.0 * (t ** 2) * (p3 - p2)
    )


def _collect_bezier_segments_local(curve_obj: bpy.types.Object) -> list[tuple[Vector, Vector, Vector, Vector]]:
    """收集曲线各段局部三次贝塞尔控制点。"""
    curve_data = curve_obj.data
    if curve_data is None:
        return []
    segments: list[tuple[Vector, Vector, Vector, Vector]] = []
    for spline in curve_data.splines:
        if spline.type != "BEZIER":
            continue
        pt_count = len(spline.bezier_points)
        if pt_count < 2:
            continue
        cyclic = spline.use_cyclic_u
        seg_count = pt_count if cyclic else pt_count - 1
        for seg_i in range(seg_count):
            bp0 = spline.bezier_points[seg_i]
            bp1 = spline.bezier_points[(seg_i + 1) % pt_count]
            segments.append((bp0.co, bp0.handle_right, bp1.handle_left, bp1.co))
    return segments


def evaluate_bezier_curve_at_t(curve_obj: bpy.types.Object, t: float) -> tuple[Vector, Vector]:
    """在归一化参数 t∈[0,1) 上直接求值贝塞尔曲线（世界坐标 + 切线）。"""
    segments = _collect_bezier_segments_local(curve_obj)
    if not segments:
        zero = curve_obj.matrix_world.translation.copy()
        return zero, Vector((0.0, 1.0, 0.0))

    t = t % 1.0
    seg_count = len(segments)
    scaled = t * seg_count
    idx = min(int(scaled), seg_count - 1)
    local_t = scaled - idx
    p0, p1, p2, p3 = segments[idx]
    local_pos = _cubic_bezier_point(p0, p1, p2, p3, local_t)
    local_tan = _cubic_bezier_tangent(p0, p1, p2, p3, local_t)
    mw = curve_obj.matrix_world
    loc = mw @ local_pos
    tangent = mw.to_3x3() @ local_tan
    tangent.z = 0.0
    if tangent.length > 1e-6:
        tangent.normalize()
    else:
        tangent = Vector((0.0, 1.0, 0.0))
    return loc, tangent


def _loop_center_xy_for_boat(curve_obj: bpy.types.Object | None = None) -> Vector:
    city = get_city_xy_center()
    if city is not None:
        return Vector((city.x, city.y, 0.0))
    lake = get_water_xy_center() or get_landscape_xy_center()
    if lake is not None:
        return Vector((lake.x, lake.y, 0.0))
    if curve_obj is not None:
        loc, _ = evaluate_bezier_curve_at_t(curve_obj, 0.25)
        return Vector((loc.x, loc.y, 0.0))
    return Vector((0.0, 0.0, 0.0))


def _boat_path_radius_at(
    curve_obj: bpy.types.Object,
    offset: float,
    center_xy: Vector,
) -> float:
    loc, _ = evaluate_bezier_curve_at_t(curve_obj, offset)
    return _xy_radius(loc, center_xy)


def _boat_path_max_radius(curve_obj: bpy.types.Object, center_xy: Vector, samples: int = 96) -> float:
    return max(
        _boat_path_radius_at(curve_obj, i / samples, center_xy)
        for i in range(samples)
    )


def _safe_boat_path_offset(
    curve_obj: bpy.types.Object,
    offset: float,
    *,
    min_radius_ratio: float = 0.48,
    samples: int = 192,
    exclude: list[float] | None = None,
    min_separation: float = 0.08,
) -> float:
    """在曲线上找离目标参数最近、且远离城市中心的安全点。"""
    center = _loop_center_xy_for_boat(curve_obj)
    max_r = _boat_path_max_radius(curve_obj, center)
    if max_r < 1e-3:
        return offset % 1.0
    threshold = max_r * min_radius_ratio
    desired = offset % 1.0
    blocked = exclude or []

    best_t: float | None = None
    best_dist = 1e18
    farthest_t = 0.0
    farthest_r = -1.0
    for i in range(samples):
        t = i / samples
        r = _boat_path_radius_at(curve_obj, t, center)
        if r > farthest_r:
            farthest_r = r
            farthest_t = t
        if r < threshold:
            continue
        if blocked and any(
            min(abs(t - other), 1.0 - abs(t - other)) < min_separation
            for other in blocked
        ):
            continue
        dist = min(abs(t - desired), 1.0 - abs(t - desired))
        if dist < best_dist:
            best_dist = dist
            best_t = t

    if best_t is not None:
        return best_t
    if blocked:
        for i in range(samples):
            t = i / samples
            r = _boat_path_radius_at(curve_obj, t, center)
            if r < threshold:
                continue
            if all(
                min(abs(t - other), 1.0 - abs(t - other)) >= min_separation
                for other in blocked
            ):
                return t
    return farthest_t


def distributed_boat_path_offsets(curve_obj: bpy.types.Object, count: int) -> list[float]:
    """沿闭合船行曲线均匀分布起点，并避开城市中心。"""
    if count <= 0:
        return []
    spacing = 1.0 / max(count, 1)
    min_gap = max(0.08, 0.75 / max(count, 1))
    placed: list[float] = []
    for i in range(count):
        desired = ((i + 0.5) * spacing) % 1.0
        candidate = _safe_boat_path_offset(
            curve_obj,
            desired,
            exclude=placed,
            min_separation=min_gap,
        )
        placed.append(candidate % 1.0)
    return placed


def _sample_bezier_curve_ordered(curve_obj: bpy.types.Object, samples: int) -> list[Vector]:
    """按控制点顺序做三次贝塞尔采样，避免网格顶点乱序或控制点直线插值抄近路。"""
    curve_data = curve_obj.data
    if curve_data is None or not curve_data.splines:
        return []

    curve_data.resolution_u = max(curve_data.resolution_u, 24)
    mw = curve_obj.matrix_world
    raw: list[Vector] = []

    for spline in curve_data.splines:
        if spline.type == "BEZIER":
            pt_count = len(spline.bezier_points)
            if pt_count < 2:
                continue
            cyclic = spline.use_cyclic_u
            seg_count = pt_count if cyclic else pt_count - 1
            per_seg = max(samples // max(seg_count, 1), 16)
            for seg_i in range(seg_count):
                bp0 = spline.bezier_points[seg_i]
                bp1 = spline.bezier_points[(seg_i + 1) % pt_count]
                p0, p1, p2, p3 = bp0.co, bp0.handle_right, bp1.handle_left, bp1.co
                steps = per_seg if cyclic or seg_i < seg_count - 1 else per_seg + 1
                for step in range(steps):
                    if not cyclic and seg_i == seg_count - 1 and step == steps - 1:
                        t = 1.0
                    else:
                        t = step / per_seg
                    co = _cubic_bezier_point(p0, p1, p2, p3, t)
                    raw.append(mw @ co)
        elif spline.points:
            pt_count = len(spline.points)
            if pt_count < 2:
                continue
            cyclic = spline.use_cyclic_u
            seg_count = pt_count if cyclic else pt_count - 1
            per_seg = max(samples // max(seg_count, 1), 8)
            for seg_i in range(seg_count):
                co0 = spline.points[seg_i].co
                co1 = spline.points[(seg_i + 1) % pt_count].co
                p0 = Vector((co0[0], co0[1], co0[2]))
                p1 = Vector((co1[0], co1[1], co1[2]))
                for step in range(per_seg):
                    t = step / per_seg
                    raw.append(mw @ p0.lerp(p1, t))

    return _dedupe_polyline_points(raw)


def _refine_loop_avoid_interior_cuts(
    points: list[Vector],
    *,
    center_xy: Vector | None = None,
    interior_radius_ratio: float = 0.58,
    max_passes: int = 8,
) -> list[Vector]:
    """细分中点落入环内过深的弦段，避免动画穿过城市/湖心。"""
    if len(points) < 4:
        return points

    center = center_xy
    if center is None:
        city = get_city_xy_center()
        center = Vector((city.x, city.y, 0.0)) if city is not None else None
    if center is None:
        avg = sum(points, Vector()) / len(points)
        center = Vector((avg.x, avg.y, 0.0))

    refined = [p.copy() for p in points]
    for _ in range(max_passes):
        radii = [_xy_radius(p, center) for p in refined]
        max_r = max(radii)
        if max_r < 1e-3:
            break
        threshold = max_r * interior_radius_ratio
        changed = False
        next_pts: list[Vector] = []
        count = len(refined)
        for i in range(count):
            p0 = refined[i]
            p1 = refined[(i + 1) % count]
            next_pts.append(p0.copy())
            seg_len = (p1 - p0).length
            if seg_len < 1.5:
                continue
            mid = p0.lerp(p1, 0.5)
            if _xy_radius(mid, center) < threshold:
                next_pts.append(mid)
                changed = True
        if not changed:
            break
        refined = next_pts
        if len(refined) > 4096:
            break
    return _dedupe_polyline_points(refined)


def _finalize_manual_loop_points(
    curve_obj: bpy.types.Object,
    points: list[Vector],
    *,
    samples: int,
) -> list[Vector]:
    """手动画/船只闭合路径的后处理。"""
    if len(points) < 2:
        return points
    closed = _close_polyline_points(_dedupe_polyline_points(points))
    eff_samples = max(samples, 640 if curve_obj.name == MANUAL_PATH_BOAT else 512)
    resampled = _resample_polyline_uniform(closed, eff_samples)
    if curve_obj.name == MANUAL_PATH_BOAT:
        lake = get_water_xy_center() or get_landscape_xy_center() or get_city_xy_center()
        center_xy = Vector((lake.x, lake.y, 0.0)) if lake is not None else None
        resampled = _refine_loop_avoid_interior_cuts(
            resampled,
            center_xy=center_xy,
            interior_radius_ratio=0.60,
        )
        return _split_long_loop_segments(resampled, max_ratio=0.012, min_max_len=2.0)
    if curve_obj.name in _MANUAL_CAR_PATH_NAMES or curve_obj.name in _MANUAL_PED_PATH_NAMES:
        return _split_long_loop_segments(resampled, max_ratio=0.025)
    if curve_obj.name == SCG_PATH_BOAT_LOOP:
        return _split_long_loop_segments(resampled, max_ratio=0.05)
    return resampled


def _curve_world_points(curve_obj: bpy.types.Object, samples: int = 256) -> list[Vector]:
    """沿曲线均匀采样世界坐标（闭合），优先用求值网格保证贝塞尔正确。"""
    curve_data = curve_obj.data
    if curve_data is None or not curve_data.splines:
        return []

    if _is_manual_path_curve(curve_obj):
        raw = _sample_bezier_curve_ordered(curve_obj, max(samples, 640))
        if len(raw) >= 2:
            return _finalize_manual_loop_points(curve_obj, raw, samples=samples)

    curve_data.resolution_u = max(curve_data.resolution_u, 24)
    mw = curve_obj.matrix_world
    raw: list[Vector] = []

    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = curve_obj.evaluated_get(depsgraph)
        temp_mesh = eval_obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        if temp_mesh and temp_mesh.vertices:
            for vert in temp_mesh.vertices:
                raw.append(mw @ vert.co.copy())
        eval_obj.to_mesh_clear()
    except (RuntimeError, AttributeError, ReferenceError):
        raw = []

    if len(raw) < 2:
        for spline in curve_data.splines:
            if spline.type == "BEZIER":
                pt_count = len(spline.bezier_points)
                if pt_count < 2:
                    continue
                for i in range(samples):
                    u = i / samples
                    idx = int(u * pt_count) % pt_count
                    nxt = (idx + 1) % pt_count
                    alpha = u * pt_count - idx
                    p0 = spline.bezier_points[idx].co
                    p1 = spline.bezier_points[nxt].co
                    raw.append(mw @ p0.lerp(p1, alpha))
            elif spline.points:
                pt_count = len(spline.points)
                for i in range(samples):
                    idx = int((i / samples) * pt_count) % pt_count
                    co = spline.points[idx].co
                    raw.append(mw @ Vector((co[0], co[1], co[2])))

    if len(raw) < 2:
        return raw

    cleaned = _dedupe_polyline_points(raw)
    closed = _close_polyline_points(cleaned)
    eff_samples = max(samples, 64)
    resampled = _resample_polyline_uniform(closed, eff_samples)
    if curve_obj.name in {SCG_PATH_BOAT_LOOP, MANUAL_PATH_BOAT}:
        return _split_long_loop_segments(resampled, max_ratio=0.05)
    if curve_obj.name in _MANUAL_CAR_PATH_NAMES or curve_obj.name in _MANUAL_PED_PATH_NAMES:
        return _split_long_loop_segments(resampled, max_ratio=0.03)
    return _sanitize_loop_path_points(resampled)


def _loop_total_length(points: list[Vector]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    count = len(points)
    for i in range(count):
        total += (points[(i + 1) % count] - points[i]).length
    return total


def _split_long_loop_segments(
    points: list[Vector],
    max_ratio: float = 0.10,
    *,
    min_max_len: float = 6.0,
) -> list[Vector]:
    """拆分过长弦，避免闭合路径动画抄近路穿过环心。"""
    if len(points) < 4:
        return points
    total = _loop_total_length(points)
    if total < 1e-3:
        return points
    max_len = max(total * max_ratio, min_max_len)
    refined: list[Vector] = []
    count = len(points)
    for i in range(count):
        p0 = points[i]
        p1 = points[(i + 1) % count]
        seg_len = (p1 - p0).length
        refined.append(p0.copy())
        if seg_len > max_len:
            steps = max(int(math.ceil(seg_len / max_len)), 2)
            for step in range(1, steps):
                alpha = step / steps
                refined.append(p0.lerp(p1, alpha))
    return _dedupe_polyline_points(refined)


def _sanitize_loop_path_points(points: list[Vector]) -> list[Vector]:
    if len(points) < 4:
        return points
    center = _path_xy_center(points)
    pruned = _prune_path_centroid_spikes(points, center)
    split = _split_long_loop_segments(pruned)
    return _phase_path_start_on_perimeter(split, center)


def _lerp_loop_parameter(t0: float, t1: float, alpha: float, *, forward: bool) -> float:
    """沿闭合曲线参数最短弧插值。"""
    if forward:
        delta = t1 - t0
        if delta < 0.0:
            delta += 1.0
        return (t0 + delta * alpha) % 1.0
    delta = t0 - t1
    if delta < 0.0:
        delta += 1.0
    return (t0 - delta * alpha) % 1.0


def _densify_path_samples(
    samples: list[tuple[float, float]],
    path_points: list[Vector],
    *,
    forward: bool,
    max_step_ratio: float = 0.06,
    max_step_min: float = 2.5,
) -> list[tuple[float, float]]:
    """相邻关键帧空间距离过大时插入中间帧，避免线性插值抄近路。"""
    if len(samples) < 2:
        return samples
    total = _loop_total_length(path_points)
    max_step = max(total * max_step_ratio, max_step_min)
    dense: list[tuple[float, float]] = [samples[0]]
    for frame, t1 in samples[1:]:
        f0, t0 = dense[-1]
        loc0, _ = _interpolate_closed_points(path_points, t0 % 1.0)
        loc1, _ = _interpolate_closed_points(path_points, t1 % 1.0)
        dist = (loc1 - loc0).length
        if dist > max_step and frame > f0:
            steps = int(math.ceil(dist / max_step))
            for step in range(1, steps):
                alpha = step / steps
                f_mid = f0 + (frame - f0) * alpha
                t_mid = _lerp_loop_parameter(t0, t1, alpha, forward=forward)
                dense.append((f_mid, t_mid))
        dense.append((frame, t1))
    return dense


def _prepare_curve_for_animation(curve_obj: bpy.types.Object, surface_z: float) -> None:
    """对齐曲线高度并确保可循环采样。"""
    if curve_obj.data is None:
        return
    curve_obj.data.use_path = True
    for spline in curve_obj.data.splines:
        spline.use_cyclic_u = True
    # 将曲线整体 Z 平移到道路顶面（保留 XY 形状）
    points = _curve_world_points(curve_obj, samples=32)
    if not points:
        return
    avg_z = sum(p.z for p in points) / len(points)
    curve_obj.location.z += surface_z - avg_z


def _interpolate_closed_points(
    points: list[Vector],
    t: float,
) -> tuple[Vector, Vector]:
    """t∈[0,1) 闭合插值，返回 (位置, 切线)。"""
    if len(points) < 2:
        zero = points[0] if points else Vector((0.0, 0.0, 0.0))
        return zero, Vector((0.0, 1.0, 0.0))

    t = t % 1.0
    segs: list[tuple[float, float, Vector, Vector]] = []
    total = 0.0
    count = len(points)
    for i in range(count):
        p0 = points[i]
        p1 = points[(i + 1) % count]
        seg_len = (p1 - p0).length
        if seg_len < 1e-6:
            continue
        segs.append((total, total + seg_len, p0, p1))
        total += seg_len

    if total < 1e-6 or not segs:
        return points[0], Vector((0.0, 1.0, 0.0))

    dist_target = (t % 1.0) * total
    for start_d, end_d, p0, p1 in segs:
        if dist_target <= end_d + 1e-6:
            seg_len = end_d - start_d
            if seg_len < 1e-6:
                tangent = p1 - p0
                pos = p0
            else:
                alpha = (dist_target - start_d) / seg_len
                alpha = max(0.0, min(1.0, alpha))
                pos = p0.lerp(p1, alpha)
                tangent = p1 - p0
            tangent.z = 0.0
            if tangent.length > 1e-6:
                tangent.normalize()
            else:
                tangent = Vector((0.0, 1.0, 0.0))
            return pos, tangent

    p0, p1 = segs[-1][2], segs[-1][3]
    tangent = p1 - p0
    if tangent.length > 1e-6:
        tangent.normalize()
    else:
        tangent = Vector((0.0, 1.0, 0.0))
    return p1, tangent


def _rotation_from_tangent(tangent: Vector, forward_local: Vector) -> tuple[float, float, float]:
    """将物体本地 forward 轴对齐到切线方向（Z 朝上）。"""
    if tangent.length < 1e-6:
        return (0.0, 0.0, 0.0)
    tangent = Vector((tangent.x, tangent.y, 0.0))
    if tangent.length < 1e-6:
        return (0.0, 0.0, 0.0)
    tangent.normalize()
    # 资产经 180° 校正后本地 -Y 为车头；to_track_quat 比 rotation_difference 更稳
    if forward_local.y < 0.0:
        quat = tangent.to_track_quat("-Y", "Z")
    else:
        quat = tangent.to_track_quat("Y", "Z")
    return quat.to_euler()


def prepare_path_curve_for_animation(curve_obj: bpy.types.Object, surface_z: float) -> None:
    """对齐单条路径曲线高度（可重复调用，高度对齐具幂等性）。"""
    _prepare_curve_for_animation(curve_obj, surface_z)


def prepare_manual_boat_path_for_animation(
    curve_obj: bpy.types.Object,
    water_z: float,
) -> None:
    """
    手动画船只曲线：保留用户绘制的 XY 轨迹，对齐湖面高度并确保闭合可采样。
    """
    if curve_obj.type != "CURVE" or curve_obj.data is None:
        return
    curve_data = curve_obj.data
    curve_data.use_path = True
    curve_data.resolution_u = max(curve_data.resolution_u, 16)
    for spline in curve_data.splines:
        spline.use_cyclic_u = True

    points = _curve_world_points(curve_obj, samples=64)
    if not points:
        return
    avg_z = sum(p.z for p in points) / len(points)
    curve_obj.location.z += water_z - avg_z


def _snap_boat_location_to_water(
    loc: Vector,
    *,
    water_objs: list[bpy.types.Object],
    fallback_z: float,
    float_z: float = 0.0,
) -> Vector:
    """沿手动画曲线 XY 贴水面高度，并抬高船体吃水线。"""
    snapped = loc.copy()
    snapped.z = water_surface_z_at_xy(loc.x, loc.y, water_objs, fallback_z) + float_z
    return snapped


def _is_on_road_loop(loc: Vector, path_points: list[Vector]) -> bool:
    """位置是否靠近环路（不在城市中心绿地里）。"""
    if len(path_points) < 4:
        return True
    center = _path_xy_center(path_points)
    loc_r = _xy_radius(loc, center)
    radii = [_xy_radius(p, center) for p in path_points]
    max_r = max(radii)
    return loc_r >= max_r * 0.45


def _safe_path_offset(
    path_points: list[Vector],
    offset: float,
    *,
    surface_z: float | None,
) -> float:
    """若 offset 落在环心附近，自动平移到路线上。"""
    for _ in range(36):
        loc, _ = _interpolate_closed_points(path_points, offset % 1.0)
        if surface_z is not None:
            loc.z = surface_z
        if _is_on_road_loop(loc, path_points):
            return offset % 1.0
        offset += 1.0 / 36.0
    return offset % 1.0


def add_curve_location_animation(
    obj: bpy.types.Object,
    curve_obj: bpy.types.Object,
    *,
    frame_start: int = 1,
    frame_end: int = 120,
    offset_start: float = 0.0,
    progress: float = 1.0,
    surface_z: float | None = None,
    forward_local: Vector | None = None,
    reverse: bool = False,
    skip_center_guard: bool = False,
    dense_motion: bool = False,
    snap_water_surface: bool = False,
    water_fallback_z: float | None = None,
    boat_offset_final: bool = False,
) -> bool:
    """
    沿曲线关键帧动画（位置 + 切线朝向），替代 Follow Path，避免倒着走/斜着滑。
    progress：动画期间沿闭合曲线前进的比例（可小于 1 表示未满一圈）。
    boat_offset_final：手动画船偏移已由 distributed_boat_path_offsets 确定，不再二次校正。
    """
    if curve_obj.type != "CURVE" or curve_obj.data is None:
        return False

    if surface_z is not None:
        _prepare_curve_for_animation(curve_obj, surface_z)

    use_dense = dense_motion or _is_manual_path_curve(curve_obj)
    is_manual_boat = curve_obj.name == MANUAL_PATH_BOAT
    sample_count = 768 if is_manual_boat else (512 if use_dense else 320)
    points = _curve_world_points(curve_obj, samples=sample_count)
    if len(points) < 2 and not is_manual_boat:
        return False
    if is_manual_boat and not _collect_bezier_segments_local(curve_obj):
        return False

    if is_manual_boat and not boat_offset_final:
        offset_start = _safe_boat_path_offset(curve_obj, offset_start)
    elif not skip_center_guard:
        offset_start = _safe_path_offset(points, offset_start, surface_z=surface_z)

    fwd = forward_local if forward_local is not None else Vector((0.0, -1.0, 0.0))

    for con in list(obj.constraints):
        if con.type == "FOLLOW_PATH":
            obj.constraints.remove(con)

    if obj.animation_data is None:
        obj.animation_data_create()
    action = bpy.data.actions.new(name=f"{obj.name}_PathAction")
    obj.animation_data.action = action

    span = max(frame_end - frame_start, 1)
    forward_motion = not reverse
    sign = 1.0 if forward_motion else -1.0

    raw_samples: list[tuple[float, float]] = []
    for frame in range(frame_start, frame_end + 1):
        alpha = (frame - frame_start) / span
        t_raw = offset_start + sign * progress * alpha
        raw_samples.append((float(frame), t_raw))

    def _loc_tan_at(t_val: float) -> tuple[Vector, Vector]:
        if is_manual_boat:
            return evaluate_bezier_curve_at_t(curve_obj, t_val % 1.0)
        return _interpolate_closed_points(points, t_val % 1.0)

    if is_manual_boat:
        dense_boat: list[tuple[float, float]] = [raw_samples[0]]
        max_step = 0.45
        for frame, t1 in raw_samples[1:]:
            f0, t0 = dense_boat[-1]
            loc0, _ = evaluate_bezier_curve_at_t(curve_obj, t0 % 1.0)
            loc1, _ = evaluate_bezier_curve_at_t(curve_obj, t1 % 1.0)
            dist = (loc1 - loc0).length
            if dist > max_step and frame > f0:
                steps = int(math.ceil(dist / max_step))
                for step in range(1, steps):
                    alpha = step / steps
                    f_mid = f0 + (frame - f0) * alpha
                    t_mid = _lerp_loop_parameter(t0, t1, alpha, forward=forward_motion)
                    dense_boat.append((f_mid, t_mid))
            dense_boat.append((frame, t1))
        samples = dense_boat
    elif use_dense:
        samples = _densify_path_samples(
            raw_samples,
            points,
            forward=forward_motion,
            max_step_ratio=0.018,
            max_step_min=1.0,
        )
    else:
        samples = _densify_path_samples(raw_samples, points, forward=forward_motion)

    water_objs: list[bpy.types.Object] = []
    if snap_water_surface and water_fallback_z is not None:
        water_objs = get_scg_water_objects()
    boat_float_z = float(obj.get("scg_boat_float_z", 0.0)) if snap_water_surface else 0.0

    for frame_f, t_raw in samples:
        t = t_raw % 1.0
        loc, tangent = _loc_tan_at(t)
        if snap_water_surface and water_fallback_z is not None:
            loc = _snap_boat_location_to_water(
                loc,
                water_objs=water_objs,
                fallback_z=water_fallback_z,
                float_z=boat_float_z,
            )
        elif surface_z is not None:
            loc.z = surface_z
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame_f)

        rot = _rotation_from_tangent(tangent, fwd)
        obj.rotation_euler = rot
        obj.keyframe_insert(data_path="rotation_euler", frame=frame_f)

    if obj.animation_data and obj.animation_data.action:
        for fcurve in obj.animation_data.action.fcurves:
            fcurve.extrapolation = "CONSTANT"
            for kp in fcurve.keyframe_points:
                kp.interpolation = "LINEAR"
                kp.handle_left_type = "AUTO"
                kp.handle_right_type = "AUTO"

    t0 = offset_start % 1.0
    loc0, tan0 = _loc_tan_at(t0)
    if snap_water_surface and water_fallback_z is not None:
        loc0 = _snap_boat_location_to_water(
            loc0,
            water_objs=water_objs,
            fallback_z=water_fallback_z,
            float_z=boat_float_z,
        )
    elif surface_z is not None:
        loc0.z = surface_z
    obj.location = loc0
    obj.rotation_euler = _rotation_from_tangent(tan0, fwd)

    return True


def create_offset_path_curve(
    name: str,
    start: Vector,
    end: Vector,
    *,
    lateral_offset: float,
    surface_z: float,
    reverse: bool = False,
) -> bpy.types.Object:
    """沿道路中心线创建曲线，并按 lateral_offset 向右侧偏移。"""
    p0, p1 = start, end
    if reverse:
        p0, p1 = p1, p0
    right = _path_right_vector(p0, p1)
    lateral = right * lateral_offset
    points = [
        Vector((p0.x + lateral.x, p0.y + lateral.y, surface_z)),
        Vector((p1.x + lateral.x, p1.y + lateral.y, surface_z)),
    ]
    return _curve_from_points(name, points)


def create_loop_path_curve(
    name: str,
    loop_segments: list[tuple[Vector, Vector]],
    *,
    lateral_offset: float,
    surface_z: float,
    loop_center: Vector,
    reverse: bool = False,
    inward: bool = True,
) -> bpy.types.Object:
    """兼容旧接口。"""
    if inward:
        return create_lane_loop_curve(
            name,
            loop_segments,
            lateral_offset=lateral_offset,
            surface_z=surface_z,
            loop_center=loop_center,
            lane_band=1.0,
            reverse=reverse,
        )
    return create_sidewalk_loop_curve(
        name,
        loop_segments,
        lateral_offset=lateral_offset,
        surface_z=surface_z,
        loop_center=loop_center,
        outer=True,
        reverse=reverse,
    )


def link_path_to_collection(curve_obj: bpy.types.Object) -> None:
    path_coll = _ensure_collection(SCG_PATH_COLLECTION)
    path_coll.hide_viewport = True
    path_coll.hide_render = True
    for user_coll in list(curve_obj.users_collection):
        user_coll.objects.unlink(curve_obj)
    path_coll.objects.link(curve_obj)


def extract_road_path_curves(
    context: bpy.types.Context,
    *,
    max_paths: int = 4,
) -> list[bpy.types.Object]:
    """兼容旧接口：返回道路中心线路径。"""
    surface_z = get_road_surface_z()
    curves: list[bpy.types.Object] = []
    for idx, (start, end) in enumerate(extract_street_segments(max_paths=max_paths)):
        name = f"{SCG_PATH_PREFIX}{idx + 1:02d}"
        curve_obj = create_offset_path_curve(
            name, start, end, lateral_offset=0.0, surface_z=surface_z,
        )
        link_path_to_collection(curve_obj)
        curves.append(curve_obj)
    _ = context
    return curves


def add_follow_path_animation(
    obj: bpy.types.Object,
    curve_obj: bpy.types.Object,
    *,
    frame_start: int = 1,
    frame_end: int = 120,
    offset_start: float = 0.0,
    loops: float = 1.0,
    forward_axis: str = "FORWARD_Y",
    forward_local: Vector | None = None,
    reverse_path: bool = False,
    surface_z: float | None = None,
    skip_center_guard: bool = False,
    dense_motion: bool = False,
    snap_water_surface: bool = False,
    water_fallback_z: float | None = None,
    boat_offset_final: bool = False,
) -> bool:
    """为 obj 添加沿 curve_obj 的路径动画（切线关键帧，兼容旧接口名）。"""
    _ = forward_axis
    fwd = forward_local if forward_local is not None else Vector((0.0, -1.0, 0.0))
    return add_curve_location_animation(
        obj,
        curve_obj,
        frame_start=frame_start,
        frame_end=frame_end,
        offset_start=offset_start,
        progress=loops,
        surface_z=surface_z,
        forward_local=fwd,
        reverse=reverse_path,
        skip_center_guard=skip_center_guard,
        dense_motion=dense_motion,
        snap_water_surface=snap_water_surface,
        water_fallback_z=water_fallback_z,
        boat_offset_final=boat_offset_final,
    )


def cleanup_path_objects() -> None:
    """移除 SCG 路径曲线。"""
    for obj in list(bpy.data.objects):
        if obj.name.startswith(SCG_PATH_PREFIX):
            bpy.data.objects.remove(obj, do_unlink=True)

    coll = bpy.data.collections.get(SCG_PATH_COLLECTION)
    if coll is not None and len(coll.all_objects) == 0:
        bpy.data.collections.remove(coll)
