# pyright: reportMissingImports=false, reportInvalidTypeForm=false
"""
阶段四：布局控制。


支持两条链路：
1. 手动输入点集 / 边集（JSON 或 Python 字面量）后，重建 `ICity Base` 的道路图。
2. 从草图图像中提取点线关系，写回输入框，并可直接应用到场景。
"""

from __future__ import annotations

import ast
import json
import math
import traceback
from collections import deque

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast


import bmesh
import bpy

from ..core.city_generator import (
    DENSITY_FLOOR_RANGE,
    _apply_road_node_object,
    _apply_road_texture,
    _fill_attribute,
    _flush_viewport_refresh,
    _object_from_collection,
    _refresh_procedural_buildings,
    _sync_icity_scene_props_for_ui,
    _type_enum_to_index,
    ensure_icity_started,
    icity_scene_ready,
    restore_base_city_from_scene,
    restore_icity_base_mesh,
)



# 单块矩形：与「生成基础城市」footprint 接近（团队实测约 432×334m，整数便于阅读）
_DEMO_LAYOUT_NAME = "单块矩形示例"
_DEMO_LAYOUT_WIDTH = 432
_DEMO_LAYOUT_DEPTH = 334

_DEMO_EDGES = [
    [0, 1],
    [1, 2],
    [2, 3],
    [3, 0],
]


def _snap_demo_dimension(value: float) -> int:
    """示例布局尺寸取整；偶数便于以整数游标为中心时角点也为整数。"""
    size = max(4, int(round(value)))
    if size % 2:
        size += 1
    return size


def _demo_layout_footprint(context: bpy.types.Context) -> tuple[int, int]:
    """若已生成城市，优先用当前道路/建筑包围盒；否则用默认整数尺寸。"""
    try:
        from ..core.city_generator import icity_scene_ready
        from ..core.scene_enhance import get_city_bounds

        if icity_scene_ready():
            city = get_city_bounds()
            if city is not None:
                _center, _half, size = city
                if size.x > 50.0 and size.y > 50.0:
                    return (
                        _snap_demo_dimension(size.x),
                        _snap_demo_dimension(size.y),
                    )
    except Exception:
        pass
    return _DEMO_LAYOUT_WIDTH, _DEMO_LAYOUT_DEPTH


def _format_demo_layout_json(data: Any) -> str:
    """示例 JSON 缩进排版，坐标均为整数，便于在输入框中阅读。"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _rectangle_points_centered(
    cx: float,
    cy: float,
    cz: float,
    width: float,
    depth: float,
) -> list[tuple[float, float, float]]:
    half_w = width * 0.5
    half_d = depth * 0.5
    return [
        (cx - half_w, cy - half_d, cz),
        (cx + half_w, cy - half_d, cz),
        (cx + half_w, cy + half_d, cz),
        (cx - half_w, cy + half_d, cz),
    ]


def _translate_layout_to_cursor(
    points: Sequence[tuple[float, float, float]],
    cursor: bpy.types.Vector,
    *,
    enabled: bool,
) -> list[tuple[float, float, float]]:
    """将点集几何中心平移到 3D 游标（仅 XY），与生成基础城市视觉居中一致。"""
    pts = list(points)
    if not enabled or not pts:
        return pts
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    ox, oy = cursor.x - cx, cursor.y - cy
    return [(x + ox, y + oy, z) for x, y, z in pts]





_DIRECTIONS_8 = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)

_LAYOUT_FACE_PASSTHROUGH_ATTRS = (
    "Offset x",
    "Offset y",
    "Rotation z",
    "Offset x preset",
    "Offset y preset",
    "Rotation z preset",
)

_LAYOUT_ROAD_PASSTHROUGH_ATTRS = (
    "street type",
    "Road lanes width",
    "side walk offset",
)

_LAYOUT_INTERSECTION_RESET_ATTRS = (
    ("offset", 0.0),
    ("crosswalk offset", 0.0),
)

_LAYOUT_FACE_RESET_ATTRS = (
    ("Offset x", 0.0),
    ("Offset y", 0.0),
    ("Rotation z", 0.0),
    ("Offset x preset", 0),
    ("Offset y preset", 0),
    ("Rotation z preset", 0),
)

_LAYOUT_DEBUG_PREFIX = "[icity.layout]"



def _layout_debug_log(message: str) -> None:
    print(f"{_LAYOUT_DEBUG_PREFIX} {message}")



def _format_debug_point(point: Sequence[float]) -> tuple[float, float, float]:
    x = float(point[0]) if len(point) > 0 else 0.0
    y = float(point[1]) if len(point) > 1 else 0.0
    z = float(point[2]) if len(point) > 2 else 0.0
    return (round(x, 3), round(y, 3), round(z, 3))



def _debug_log_points(label: str, points: Sequence[tuple[float, float, float]], *, limit: int = 16) -> None:
    if not points:
        _layout_debug_log(f"{label}: 0 points")
        return
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    centroid = (
        round(sum(xs) / len(xs), 3),
        round(sum(ys) / len(ys), 3),
        round(sum(zs) / len(zs), 3),
    )
    bbox_min = (round(min(xs), 3), round(min(ys), 3), round(min(zs), 3))
    bbox_max = (round(max(xs), 3), round(max(ys), 3), round(max(zs), 3))
    sample = [_format_debug_point(point) for point in points[:limit]]
    more = " ..." if len(points) > limit else ""
    _layout_debug_log(
        f"{label}: count={len(points)} centroid={centroid} bbox={bbox_min}->{bbox_max} sample={sample}{more}"
    )



def _debug_log_edges(
    label: str,
    points: Sequence[tuple[float, float, float]],
    edges: Sequence[tuple[int, int]],
    *,
    limit: int = 24,
) -> None:
    sample: list[dict[str, Any]] = []
    for a_idx, b_idx in edges[:limit]:
        sample.append(
            {
                "key": [int(a_idx), int(b_idx)],
                "a": _format_debug_point(points[a_idx]),
                "b": _format_debug_point(points[b_idx]),
            }
        )
    more = " ..." if len(edges) > limit else ""
    _layout_debug_log(f"{label}: count={len(edges)} sample={sample}{more}")



def _debug_log_face_cycles(
    label: str,
    points: Sequence[tuple[float, float, float]],
    faces: Sequence[Sequence[int]],
    *,
    limit: int = 16,
) -> None:
    sample: list[dict[str, Any]] = []
    for cycle in faces[:limit]:
        sample.append(
            {
                "verts": [int(idx) for idx in cycle],
                "area": round(abs(_polygon_area_xy(points, cycle)), 3),
            }
        )
    more = " ..." if len(faces) > limit else ""
    _layout_debug_log(f"{label}: count={len(faces)} sample={sample}{more}")



def _debug_log_mesh_geometry(mesh: bpy.types.Mesh, *, limit: int = 24) -> None:
    verts = [_format_debug_point(vertex.co) for vertex in mesh.vertices[: min(len(mesh.vertices), limit)]]
    edges: list[dict[str, Any]] = []
    for edge in mesh.edges[: min(len(mesh.edges), limit)]:
        a_idx = int(edge.vertices[0])
        b_idx = int(edge.vertices[1])
        edges.append(
            {
                "key": [a_idx, b_idx],
                "a": _format_debug_point(mesh.vertices[a_idx].co),
                "b": _format_debug_point(mesh.vertices[b_idx].co),
            }
        )
    polys = [[int(v) for v in poly.vertices] for poly in mesh.polygons[: min(len(mesh.polygons), limit)]]
    _layout_debug_log(
        f"mesh geometry: verts={len(mesh.vertices)} edges={len(mesh.edges)} polys={len(mesh.polygons)} "
        f"vert_sample={verts}{' ...' if len(mesh.vertices) > limit else ''}"
    )
    _layout_debug_log(f"mesh edges sample={edges}{' ...' if len(mesh.edges) > limit else ''}")
    _layout_debug_log(f"mesh polys sample={polys}{' ...' if len(mesh.polygons) > limit else ''}")



def _debug_log_attribute(mesh: bpy.types.Mesh, name: str, *, limit: int = 16) -> None:
    attr = mesh.attributes.get(name)
    if attr is None:
        _layout_debug_log(f"attr {name}: <missing>")
        return
    values: list[Any] = []
    for item in attr.data[: min(len(attr.data), limit)]:
        if hasattr(item, "value"):
            value = item.value
            if isinstance(value, float):
                value = round(value, 4)
            values.append(value)
        else:
            values.append("<no value>")
    _layout_debug_log(
        f"attr {name}: domain={attr.domain} type={attr.data_type} len={len(attr.data)} sample={values}"
        f"{' ...' if len(attr.data) > limit else ''}"
    )



def _set_layout_status(scene: bpy.types.Scene, message: str) -> None:

    scene.scg_layout_status = message[:1024]


def _has_landscape_surround() -> bool:
    root = bpy.data.objects.get("SCG_Landscape_Surround")
    if root is not None:
        return True
    eco = bpy.data.collections.get("SCG_Ecology")
    return eco is not None and len(eco.all_objects) > 0


def _has_dynamic_elements() -> bool:
    dyn_coll = bpy.data.collections.get("SCG_Dynamics")
    if dyn_coll is not None and len(dyn_coll.all_objects) > 0:
        return True
    path_coll = bpy.data.collections.get("SCG_Paths")
    if path_coll is not None and len(path_coll.all_objects) > 0:
        return True
    for obj in bpy.data.objects:
        if obj.name.startswith(("SCG_Car_", "SCG_Ped_", "SCG_Path_")):
            return True
    return False


def _sync_dependent_scene_objects_after_layout(
    context: bpy.types.Context,
) -> list[str]:
    notes: list[str] = []
    had_landscape = _has_landscape_surround()
    had_dynamics = _has_dynamic_elements()

    if had_landscape:
        try:
            from ..core.scene_enhance import add_landscape_surround, cleanup_landscape_surround

            cleanup_landscape_surround(context)
            ok, message = add_landscape_surround(context)
            notes.append("山水已按新城市位置重建" if ok else f"山水未能自动重建：{message}")
        except Exception as exc:
            notes.append(f"山水未能自动重建：{exc}")

    if had_dynamics:
        try:
            from ..core.dynamic_elements import add_cars_and_pedestrians, cleanup_dynamic_elements

            cleanup_dynamic_elements(context)
            ok, message = add_cars_and_pedestrians(context)
            notes.append("车人与路径已按新道路重建" if ok else f"车人与路径未能自动重建：{message}")
        except Exception as exc:
            notes.append(f"车人与路径未能自动重建：{exc}")

    return notes






def _format_compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _parse_literal(text: str, label: str) -> Any:
    payload = (text or "").strip()
    if not payload:
        raise ValueError(f"{label}不能为空")

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    try:
        return ast.literal_eval(payload)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(f"{label}格式错误，请输入 JSON 或 Python 列表/元组") from exc


def _to_float(value: object, label: str) -> float:
    try:
        return float(cast(float | int | str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc


def _to_int(value: object, label: str) -> int:
    try:
        return int(cast(int | float | str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是整数") from exc


def _edge_key(a_idx: int, b_idx: int) -> tuple[int, int]:
    return (a_idx, b_idx) if a_idx <= b_idx else (b_idx, a_idx)


_LAYOUT_COORD_PRECISION = 4



def _point_coord_key(point: Sequence[float]) -> tuple[float, float, float]:
    x = float(point[0]) if len(point) > 0 else 0.0
    y = float(point[1]) if len(point) > 1 else 0.0
    z = float(point[2]) if len(point) > 2 else 0.0
    return (
        round(x, _LAYOUT_COORD_PRECISION),
        round(y, _LAYOUT_COORD_PRECISION),
        round(z, _LAYOUT_COORD_PRECISION),
    )



def _edge_coord_key(
    a_point: Sequence[float],
    b_point: Sequence[float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    a_key = _point_coord_key(a_point)
    b_key = _point_coord_key(b_point)
    return (a_key, b_key) if a_key <= b_key else (b_key, a_key)



def _segment_key(

    a_cell: tuple[int, int],
    b_cell: tuple[int, int],
) -> tuple[tuple[int, int], tuple[int, int]]:
    return (a_cell, b_cell) if a_cell <= b_cell else (b_cell, a_cell)


def _normalize_point(raw: Any, index: int) -> tuple[float, float, float]:

    if isinstance(raw, dict):
        if "x" not in raw or "y" not in raw:
            raise ValueError(f"点集第 {index} 项缺少 x/y")
        x = raw["x"]
        y = raw["y"]
        z = raw.get("z", 0.0)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        if len(raw) not in (2, 3):
            raise ValueError(f"点集第 {index} 项必须是 [x,y] 或 [x,y,z]")
        x = raw[0]
        y = raw[1]
        z = raw[2] if len(raw) == 3 else 0.0
    else:
        raise ValueError(f"点集第 {index} 项不是有效坐标")

    return (
        _to_float(x, f"点集第 {index} 项的 x"),
        _to_float(y, f"点集第 {index} 项的 y"),
        _to_float(z, f"点集第 {index} 项的 z"),
    )



def _normalize_edge(raw: Any, index: int, point_count: int) -> tuple[int, int]:
    if isinstance(raw, dict):
        if "a" in raw and "b" in raw:
            a = raw["a"]
            b = raw["b"]
        elif "start" in raw and "end" in raw:
            a = raw["start"]
            b = raw["end"]
        else:
            raise ValueError(f"边集第 {index} 项缺少 a/b 或 start/end")
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) == 2:
        a, b = raw
    else:
        raise ValueError(f"边集第 {index} 项必须是 [i,j] 或 {{a,b}}")

    a_i = _to_int(a, f"边集第 {index} 项起点")
    b_i = _to_int(b, f"边集第 {index} 项终点")


    if a_i == b_i:
        raise ValueError(f"边集第 {index} 项起点和终点不能相同")
    if not (0 <= a_i < point_count and 0 <= b_i < point_count):
        raise ValueError(f"边集第 {index} 项索引越界，点集数量为 {point_count}")

    return (a_i, b_i)


def parse_layout_inputs(points_text: str, edges_text: str) -> tuple[list[tuple[float, float, float]], list[tuple[int, int]]]:
    points_source = _parse_literal(points_text, "点集 JSON")
    edges_source: Any

    if isinstance(points_source, dict) and "points" in points_source:
        edges_source = points_source.get("edges", []) if not (edges_text or "").strip() else _parse_literal(edges_text, "边集 JSON")
        points_source = points_source["points"]
    else:
        edges_source = _parse_literal(edges_text, "边集 JSON")

    if not isinstance(points_source, Sequence) or isinstance(points_source, (str, bytes)):
        raise ValueError("点集必须是数组")
    if not isinstance(edges_source, Sequence) or isinstance(edges_source, (str, bytes)):
        raise ValueError("边集必须是数组")

    points = [_normalize_point(item, i) for i, item in enumerate(points_source)]
    if len(points) < 2:
        raise ValueError("至少需要 2 个点")

    edges: list[tuple[int, int]] = []
    seen_edges: set[tuple[int, int]] = set()
    for i, item in enumerate(edges_source):
        edge = _normalize_edge(item, i, len(points))
        key = _edge_key(edge[0], edge[1])
        if key in seen_edges:
            continue
        seen_edges.add(key)

        edges.append(edge)

    if not edges:
        raise ValueError("至少需要 1 条边")

    return points, edges


def _activate_icity_base(context: bpy.types.Context) -> bpy.types.Object:
    if not ensure_icity_started():
        raise ValueError("Start 失败：未找到 ICity Base")

    obj = bpy.data.objects.get("ICity Base")
    if obj is None:
        raise ValueError("未找到 ICity Base")

    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    for item in context.view_layer.objects:
        item.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def _convex_hull_indices(points: Sequence[tuple[float, float, float]]) -> list[int]:
    indexed = []
    seen_xy: set[tuple[float, float]] = set()
    for idx, (x, y, _z) in enumerate(points):
        key = (float(x), float(y))
        if key in seen_xy:
            continue
        seen_xy.add(key)
        indexed.append((float(x), float(y), idx))

    if len(indexed) < 3:
        return []

    indexed.sort(key=lambda item: (item[0], item[1], item[2]))

    def cross(o: tuple[float, float, int], a: tuple[float, float, int], b: tuple[float, float, int]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float, int]] = []
    for item in indexed:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], item) <= 0:
            lower.pop()
        lower.append(item)

    upper: list[tuple[float, float, int]] = []
    for item in reversed(indexed):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], item) <= 0:
            upper.pop()
        upper.append(item)

    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return []
    return [item[2] for item in hull]


def _capture_attribute_defaults(mesh: bpy.types.Mesh, names: Sequence[str]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for name in names:
        attr = mesh.attributes.get(name)
        if attr is None or len(attr.data) == 0:
            continue
        sample = attr.data[0]
        if hasattr(sample, "value"):
            defaults[name] = sample.value
    return defaults


def _apply_attribute_defaults(mesh: bpy.types.Mesh, defaults: dict[str, Any]) -> None:
    for name, value in defaults.items():
        _fill_attribute(mesh, name, value)


def _polygon_area_xy(points: Sequence[tuple[float, float, float]], indices: Sequence[int]) -> float:
    area = 0.0
    count = len(indices)
    for i in range(count):
        ax, ay, _az = points[indices[i]]
        bx, by, _bz = points[indices[(i + 1) % count]]
        area += ax * by - ay * bx
    return area * 0.5


def _interior_point_indices_on_segment(
    a_idx: int,
    b_idx: int,
    points: Sequence[tuple[float, float, float]],
    *,
    eps: float = 1e-4,
) -> list[int]:
    """凸包边若跳过共线中间点（如 0→2 经过点 1），则不应添加该弦边。"""
    ax, ay, _az = points[a_idx]
    bx, by, _bz = points[b_idx]
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= eps * eps:
        return []

    interior: list[int] = []
    for idx, (px, py, _pz) in enumerate(points):
        if idx in (a_idx, b_idx):
            continue
        t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
        if t <= eps or t >= 1.0 - eps:
            continue
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        dist_sq = (px - proj_x) ** 2 + (py - proj_y) ** 2
        if dist_sq <= eps * eps:
            interior.append(idx)
    return interior


def _point_in_polygon_xy(
    px: float,
    py: float,
    cycle: Sequence[int],
    points: Sequence[tuple[float, float, float]],
) -> bool:
    """射线法；用于剔除包含其它网格顶点的「大面」。"""
    inside = False
    count = len(cycle)
    for i in range(count):
        ax, ay, _az = points[cycle[i]]
        bx, by, _bz = points[cycle[(i + 1) % count]]
        if ((ay > py) != (by > py)) and (
            px < (bx - ax) * (py - ay) / (by - ay + 1e-12) + ax
        ):
            inside = not inside
    return inside


def _is_minimal_face_cycle(
    cycle: Sequence[int],
    points: Sequence[tuple[float, float, float]],
) -> bool:
    """只保留内部不含其它输入顶点的面（网格单元），去掉外圈大面。"""
    for idx, (px, py, _pz) in enumerate(points):
        if idx in cycle:
            continue
        if _point_in_polygon_xy(px, py, cycle, points):
            return False
    return True


def _normalize_face_cycle_ccw(
    cycle: list[int],
    points: Sequence[tuple[float, float, float]],
) -> list[int]:
    if _polygon_area_xy(points, cycle) < 0.0:
        return list(reversed(cycle))
    return cycle


def _dedupe_face_cycles(faces: list[list[int]]) -> list[list[int]]:
    unique: list[list[int]] = []
    seen: set[frozenset[int]] = set()
    for cycle in faces:
        key = frozenset(cycle)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cycle)
    return unique


def _build_layout_faces(

    points: Sequence[tuple[float, float, float]],
    edges: Sequence[tuple[int, int]],
    *,
    add_boundary: bool,
) -> tuple[list[tuple[int, int]], list[list[int]]]:
    all_edge_keys: set[tuple[int, int]] = {_edge_key(int(a), int(b)) for a, b in edges}

    if add_boundary:
        hull_indices = _convex_hull_indices(points)
        if len(hull_indices) >= 3:
            for i, a_idx in enumerate(hull_indices):
                b_idx = hull_indices[(i + 1) % len(hull_indices)]
                key = _edge_key(a_idx, b_idx)
                if key in all_edge_keys:
                    continue
                if _interior_point_indices_on_segment(a_idx, b_idx, points):
                    continue
                all_edge_keys.add(key)

    adjacency: dict[int, list[int]] = {idx: [] for idx in range(len(points))}
    for a_idx, b_idx in all_edge_keys:
        adjacency[a_idx].append(b_idx)
        adjacency[b_idx].append(a_idx)

    ordered_neighbors: dict[int, list[int]] = {}
    neighbor_lookup: dict[int, dict[int, int]] = {}
    for idx, neighbors in adjacency.items():
        ordered = sorted(
            set(neighbors),
            key=lambda other: math.atan2(
                points[other][1] - points[idx][1],
                points[other][0] - points[idx][0],
            ),
        )
        ordered_neighbors[idx] = ordered
        neighbor_lookup[idx] = {neighbor: pos for pos, neighbor in enumerate(ordered)}

    visited_half_edges: set[tuple[int, int]] = set()
    faces: list[list[int]] = []
    max_steps = max(1, len(all_edge_keys) * 2 + 2)

    for start_u, neighbors in ordered_neighbors.items():
        for start_v in neighbors:
            if (start_u, start_v) in visited_half_edges:
                continue

            traversed: list[tuple[int, int]] = []
            cycle: list[int] = []
            current_u = start_u
            current_v = start_v
            closed = False

            for _step in range(max_steps):
                traversed.append((current_u, current_v))
                cycle.append(current_u)

                incoming_index = neighbor_lookup[current_v].get(current_u)
                next_candidates = ordered_neighbors[current_v]
                if incoming_index is None or not next_candidates:
                    break

                next_v = next_candidates[(incoming_index - 1) % len(next_candidates)]
                current_u, current_v = current_v, next_v
                if (current_u, current_v) == (start_u, start_v):
                    closed = True
                    break

            visited_half_edges.update(traversed)

            if not closed or len(cycle) < 3:
                continue
            if len(set(cycle)) != len(cycle):
                continue

            area = abs(_polygon_area_xy(points, cycle))
            if area <= 1e-6:
                continue
            normalized = _normalize_face_cycle_ccw(cycle, points)
            if not _is_minimal_face_cycle(normalized, points):
                continue
            faces.append(normalized)

    if not faces and add_boundary:
        hull_indices = _convex_hull_indices(points)
        if len(hull_indices) >= 3:
            faces.append(_normalize_face_cycle_ccw(list(hull_indices), points))

    return sorted(all_edge_keys), _dedupe_face_cycles(faces)


def _reset_layout_face_transform_attributes(mesh: bpy.types.Mesh) -> None:
    """自定义布局应用后，强制清掉面域偏移/旋转，避免隐藏随机偏移把街区甩飞。"""
    for name, value in _LAYOUT_FACE_RESET_ATTRS:
        _fill_attribute(mesh, name, value)



def _apply_layout_face_attributes(
    mesh: bpy.types.Mesh,
    scene: bpy.types.Scene,
    preserved_defaults: dict[str, Any] | None = None,
) -> None:
    building_idx = _type_enum_to_index(scene.scg_building_type)
    floor_min, floor_max = DENSITY_FLOOR_RANGE.get(scene.scg_building_density, (4, 10))

    _fill_attribute(mesh, "space type", 0)
    _fill_attribute(mesh, "Procedural index", building_idx)
    _fill_attribute(mesh, "Park", 0)
    _fill_attribute(mesh, "Presets", 0)
    _fill_attribute(mesh, "Landscape", 0)
    _fill_attribute(mesh, "Floor count", floor_min)
    _fill_attribute(mesh, "Floor count max", floor_max)
    _apply_attribute_defaults(mesh, preserved_defaults or {})
    _reset_layout_face_transform_attributes(mesh)







def _apply_layout_edge_attributes(
    mesh: bpy.types.Mesh,
    road_edge_keys: set[tuple[tuple[float, float, float], tuple[float, float, float]]],
    preserved_defaults: dict[str, Any] | None = None,
) -> None:
    _apply_attribute_defaults(mesh, preserved_defaults or {})

    road_del_attr = mesh.attributes.get("Road del")
    tree_attr = mesh.attributes.get("Tree")
    bench_attr = mesh.attributes.get("Bench")
    light_attr = mesh.attributes.get("Light")
    matched_roads = 0

    for edge in mesh.edges:
        vert_a = mesh.vertices[int(edge.vertices[0])].co
        vert_b = mesh.vertices[int(edge.vertices[1])].co
        key = _edge_coord_key(vert_a, vert_b)
        is_road = key in road_edge_keys
        matched_roads += int(is_road)
        if road_del_attr is not None:
            road_del_attr.data[edge.index].value = not is_road
        if tree_attr is not None:
            tree_attr.data[edge.index].value = bool(is_road)
        if bench_attr is not None:
            bench_attr.data[edge.index].value = bool(is_road)
        if light_attr is not None:
            light_attr.data[edge.index].value = False

    _layout_debug_log(f"edge attr match: matched_roads={matched_roads} total_edges={len(mesh.edges)} expected_roads={len(road_edge_keys)}")




def _reset_layout_intersection_attributes(mesh: bpy.types.Mesh) -> None:
    """交叉口偏移属于顶点属性；自定义拓扑应用后统一归零，避免旧城市把路口顶飞。"""
    for name, value in _LAYOUT_INTERSECTION_RESET_ATTRS:
        _fill_attribute(mesh, name, value)



def apply_layout_graph(

    context: bpy.types.Context,
    scene: bpy.types.Scene,
    points: Sequence[tuple[float, float, float]],
    edges: Sequence[tuple[int, int]],
) -> tuple[bool, str]:
    center_on_cursor = getattr(scene, "scg_layout_center_on_cursor", True)
    cursor = context.scene.cursor.location
    _layout_debug_log(
        f"apply start: center_on_cursor={center_on_cursor} cursor={_format_debug_point((cursor.x, cursor.y, cursor.z))} "
        f"boundary_face={getattr(scene, 'scg_layout_create_boundary_face', True)}"
    )
    _debug_log_points("input points", points)
    _debug_log_edges("input edges", points, edges)

    points = _translate_layout_to_cursor(
        points,
        cursor,
        enabled=center_on_cursor,
    )
    _debug_log_points("translated points", points)

    restored, restore_message = restore_icity_base_mesh(context)
    _layout_debug_log(f"restore template: ok={restored} message={restore_message}")
    if not restored:
        return False, f"应用布局前无法重置 ICity Base：{restore_message}"

    obj = _activate_icity_base(context)
    mesh = obj.data
    _layout_debug_log(
        f"active object: location={_format_debug_point(obj.location)} scale={_format_debug_point(obj.scale)} "
        f"rotation={_format_debug_point(obj.rotation_euler)}"
    )
    preserved_face_defaults = _capture_attribute_defaults(mesh, _LAYOUT_FACE_PASSTHROUGH_ATTRS)
    preserved_road_defaults = _capture_attribute_defaults(mesh, _LAYOUT_ROAD_PASSTHROUGH_ATTRS)
    _layout_debug_log(f"captured face defaults={preserved_face_defaults}")
    _layout_debug_log(f"captured road defaults={preserved_road_defaults}")
    _debug_log_attribute(mesh, "Offset x")
    _debug_log_attribute(mesh, "Offset y")
    _debug_log_attribute(mesh, "Rotation z")
    _debug_log_attribute(mesh, "offset")
    _debug_log_attribute(mesh, "crosswalk offset")

    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(mesh)

    geom = list(bm.faces) + list(bm.edges) + list(bm.verts)
    _layout_debug_log(
        f"pre-clear bmesh: verts={len(bm.verts)} edges={len(bm.edges)} faces={len(bm.faces)} delete_geom={len(geom)}"
    )
    if geom:
        bmesh.ops.delete(bm, geom=geom, context="VERTS")

    bm.verts.ensure_lookup_table()
    new_verts = [bm.verts.new(point) for point in points]
    bm.verts.ensure_lookup_table()

    road_edge_keys = {_edge_key(int(a_idx), int(b_idx)) for a_idx, b_idx in edges}
    road_segment_keys = {_edge_coord_key(points[a_idx], points[b_idx]) for a_idx, b_idx in road_edge_keys}
    all_edge_keys, face_cycles = _build_layout_faces(
        points,
        edges,
        add_boundary=getattr(scene, "scg_layout_create_boundary_face", True),
    )
    _debug_log_edges("road edge keys(input index)", points, sorted(road_edge_keys))
    _layout_debug_log(f"road segment keys(coord)={sorted(road_segment_keys)}")
    _debug_log_edges("all edge keys", points, all_edge_keys)
    _debug_log_face_cycles("face cycles", points, face_cycles)


    for a_idx, b_idx in all_edge_keys:
        try:
            bm.edges.new((new_verts[a_idx], new_verts[b_idx]))
        except ValueError:
            pass

    created_face_count = 0
    for cycle in face_cycles:
        try:
            bm.faces.new([new_verts[idx] for idx in cycle])
            created_face_count += 1
        except ValueError:
            pass
    _layout_debug_log(f"bmesh create result: edges={len(bm.edges)} faces={len(bm.faces)} created_faces={created_face_count}")

    # 不再 fallback contextual_create：易把道路网合并成错误大面，导致「巳」形只建一块城

    bm.faces.ensure_lookup_table()
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()
    bmesh.update_edit_mesh(mesh)
    bpy.ops.object.mode_set(mode="OBJECT")

    mesh = obj.data
    building_idx = _type_enum_to_index(scene.scg_building_type)
    road_idx = _type_enum_to_index(scene.scg_road_type)
    tree_idx = _type_enum_to_index(scene.scg_tree_type)
    bench_idx = _type_enum_to_index(scene.scg_bench_type)

    _apply_layout_face_attributes(mesh, scene, preserved_face_defaults)
    _apply_layout_edge_attributes(mesh, road_segment_keys, preserved_road_defaults)
    _reset_layout_intersection_attributes(mesh)


    _debug_log_mesh_geometry(mesh)
    for attr_name in (
        "Road del",
        "space type",
        "Procedural index",
        "street type",
        "Road lanes width",
        "side walk offset",
        "Offset x",
        "Offset y",
        "Rotation z",
        "Offset x preset",
        "Offset y preset",
        "Rotation z preset",
        "offset",
        "crosswalk offset",
    ):
        _debug_log_attribute(mesh, attr_name)

    _apply_road_texture(road_idx)

    _apply_road_node_object("Light", _object_from_collection("ICity_Light", 0))
    _apply_road_node_object("Tree", _object_from_collection("ICity_Tree", tree_idx))
    _apply_road_node_object("Bench", _object_from_collection("ICity_Bench", bench_idx))
    _sync_icity_scene_props_for_ui(scene, building_idx)

    mesh.update()
    obj.update_tag(refresh={"DATA"})
    _flush_viewport_refresh()
    _refresh_procedural_buildings()
    _flush_viewport_refresh()

    sync_notes = _sync_dependent_scene_objects_after_layout(context)
    _flush_viewport_refresh()
    _layout_debug_log(f"dependent sync notes={sync_notes}")

    actual_face_count = len(mesh.polygons)
    face_info = f"，边界面={'开启' if getattr(scene, 'scg_layout_create_boundary_face', True) else '关闭'}"
    sync_info = f"；{'；'.join(sync_notes)}" if sync_notes else ""
    _layout_debug_log(
        f"apply done: mesh_faces={actual_face_count} expected_faces={len(face_cycles)} road_edges={len(road_edge_keys)}"
    )
    return True, (
        f"布局已应用：{len(points)} 个点，{len(edges)} 条道路边，"
        f"{actual_face_count} 个街区面（预期 {len(face_cycles)}）{face_info}{sync_info}；详细日志已输出到系统控制台"
    )






def _load_image_mask(image_path: str, threshold: float, max_resolution: int) -> tuple[list[list[bool]], int, int]:
    abs_path = bpy.path.abspath(image_path or "")
    if not abs_path:
        raise ValueError("请先选择草图图像")
    if not Path(abs_path).is_file():
        raise ValueError(f"图像不存在：{abs_path}")

    try:
        image = bpy.data.images.load(abs_path, check_existing=True)
    except RuntimeError as exc:
        raise ValueError(f"无法加载图像：{exc}") from exc

    width, height = int(image.size[0]), int(image.size[1])
    if width <= 0 or height <= 0:
        raise ValueError("图像尺寸无效")

    pixels = list(image.pixels[:])
    stride = max(1, int(math.ceil(max(width, height) / max(8, max_resolution))))
    sampled_width = max(1, int(math.ceil(width / stride)))
    sampled_height = max(1, int(math.ceil(height / stride)))

    mask = [[False for _x in range(sampled_width)] for _y in range(sampled_height)]

    for y in range(sampled_height):
        src_y = min(height - 1, y * stride)
        for x in range(sampled_width):
            src_x = min(width - 1, x * stride)
            index = (src_y * width + src_x) * 4
            r, g, b, a = pixels[index : index + 4]
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            mask[y][x] = a > 0.01 and luminance <= threshold

    return mask, sampled_width, sampled_height


def _dark_neighbors(mask: Sequence[Sequence[bool]], row: int, col: int) -> list[tuple[int, int]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    result: list[tuple[int, int]] = []
    for dr, dc in _DIRECTIONS_8:
        nr = row + dr
        nc = col + dc
        if 0 <= nr < height and 0 <= nc < width and mask[nr][nc]:
            result.append((nr, nc))
    return result


def _is_key_pixel(mask: Sequence[Sequence[bool]], row: int, col: int) -> bool:
    neighbors = _dark_neighbors(mask, row, col)
    degree = len(neighbors)
    if degree != 2:
        return True

    v1 = (neighbors[0][0] - row, neighbors[0][1] - col)
    v2 = (neighbors[1][0] - row, neighbors[1][1] - col)
    return (v1[0] + v2[0], v1[1] + v2[1]) != (0, 0)


def _neighbor_ring(mask: Sequence[Sequence[bool]], row: int, col: int) -> list[bool]:
    ring_offsets = (
        (-1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, -1),
    )
    height = len(mask)
    width = len(mask[0]) if height else 0
    result: list[bool] = []
    for dr, dc in ring_offsets:
        nr = row + dr
        nc = col + dc
        result.append(0 <= nr < height and 0 <= nc < width and mask[nr][nc])
    return result


def _thin_mask(mask: Sequence[Sequence[bool]]) -> list[list[bool]]:

    """使用 Zhang-Suen 细化，把粗线道路收缩为近似单像素骨架。"""
    height = len(mask)
    width = len(mask[0]) if height else 0
    if height < 3 or width < 3:
        return [list(row) for row in mask]

    result = [list(row) for row in mask]
    changed = True
    while changed:
        changed = False
        to_remove: list[tuple[int, int]] = []

        for row in range(1, height - 1):
            for col in range(1, width - 1):
                if not result[row][col]:
                    continue
                ring = _neighbor_ring(result, row, col)
                count = sum(1 for value in ring if value)
                transitions = 0
                for idx, current in enumerate(ring):
                    nxt = ring[(idx + 1) % len(ring)]
                    if not current and nxt:
                        transitions += 1
                if not (2 <= count <= 6 and transitions == 1):
                    continue
                p2, _p3, p4, _p5, p6, _p7, p8, _p9 = ring
                if p2 and p4 and p6:
                    continue
                if p4 and p6 and p8:
                    continue

                to_remove.append((row, col))

        if to_remove:
            changed = True
            for row, col in to_remove:
                result[row][col] = False

        to_remove = []
        for row in range(1, height - 1):
            for col in range(1, width - 1):
                if not result[row][col]:
                    continue
                ring = _neighbor_ring(result, row, col)
                count = sum(1 for value in ring if value)
                transitions = 0
                for idx, current in enumerate(ring):
                    nxt = ring[(idx + 1) % len(ring)]
                    if not current and nxt:
                        transitions += 1
                if not (2 <= count <= 6 and transitions == 1):
                    continue
                p2, _p3, p4, _p5, p6, _p7, p8, _p9 = ring
                if p2 and p4 and p8:
                    continue
                if p2 and p6 and p8:
                    continue

                to_remove.append((row, col))

        if to_remove:
            changed = True
            for row, col in to_remove:
                result[row][col] = False

    return result


def _connected_components(cells: Iterable[tuple[int, int]]) -> list[list[tuple[int, int]]]:

    cell_set = set(cells)
    components: list[list[tuple[int, int]]] = []
    visited: set[tuple[int, int]] = set()

    for cell in cell_set:
        if cell in visited:
            continue
        queue = deque([cell])
        visited.add(cell)
        comp: list[tuple[int, int]] = []
        while queue:
            current = queue.popleft()
            comp.append(current)
            r, c = current
            for dr, dc in _DIRECTIONS_8:
                nxt = (r + dr, c + dc)
                if nxt in cell_set and nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        components.append(comp)

    return components


def _fallback_key_pixels(mask: Sequence[Sequence[bool]]) -> list[tuple[int, int]]:
    dark_cells = [
        (row, col)
        for row in range(len(mask))
        for col in range(len(mask[0]))
        if mask[row][col]
    ]
    if not dark_cells:
        return []

    fallback: list[tuple[int, int]] = []
    for comp in _connected_components(dark_cells):
        comp_sorted = sorted(comp)
        fallback.extend(
            {
                min(comp_sorted, key=lambda item: item[0]),
                max(comp_sorted, key=lambda item: item[0]),
                min(comp_sorted, key=lambda item: item[1]),
                max(comp_sorted, key=lambda item: item[1]),
            }
        )
    return fallback


def _trace_to_next_node(
    mask: Sequence[Sequence[bool]],
    cell_to_node: dict[tuple[int, int], int],
    start_node: int,
    start_cell: tuple[int, int],
    first_step: tuple[int, int],
) -> tuple[int | None, list[tuple[tuple[int, int], tuple[int, int]]]]:
    previous = start_cell
    current = first_step
    traversed: list[tuple[tuple[int, int], tuple[int, int]]] = []

    while True:
        traversed.append(_segment_key(previous, current))

        node = cell_to_node.get(current)
        if node is not None and node != start_node:
            return node, traversed

        next_cells = [cell for cell in _dark_neighbors(mask, current[0], current[1]) if cell != previous]
        if not next_cells:
            return None, traversed

        if len(next_cells) == 1:
            previous, current = current, next_cells[0]
            continue

        # 正常情况下分叉点已经被识别为 node；这里做兜底，尽快走向最近的 node。
        for candidate in next_cells:
            node = cell_to_node.get(candidate)
            if node is not None and node != start_node:
                traversed.append(_segment_key(current, candidate))

                return node, traversed

        previous, current = current, next_cells[0]


def _snap_axis(values: Sequence[float], tolerance: float) -> list[float]:
    if not values:
        return []

    sorted_indices = sorted(range(len(values)), key=lambda idx: values[idx])
    groups: list[list[int]] = []
    current_group: list[int] = []

    for idx in sorted_indices:
        if not current_group:
            current_group = [idx]
            continue
        current_values = [values[item] for item in current_group]
        group_center = sum(current_values) / len(current_values)
        if abs(values[idx] - group_center) <= tolerance:
            current_group.append(idx)
            continue
        groups.append(current_group)
        current_group = [idx]

    if current_group:
        groups.append(current_group)

    snapped = list(values)
    for group in groups:
        center = round(sum(values[idx] for idx in group) / len(group), 3)
        for idx in group:
            snapped[idx] = center
    return snapped


def _regularize_uniform_axis(values: Sequence[float], tolerance: float) -> list[float]:
    snapped = _snap_axis(values, tolerance)
    unique = sorted({round(value, 3) for value in snapped})
    if len(unique) < 3:
        return snapped

    gaps = [unique[idx + 1] - unique[idx] for idx in range(len(unique) - 1)]
    avg_gap = sum(gaps) / len(gaps)
    if avg_gap <= 1e-6:
        return snapped

    max_dev = max(abs(gap - avg_gap) for gap in gaps)
    if max_dev > max(tolerance, avg_gap * 0.08):
        return snapped

    normalized = {
        center: round(unique[0] + avg_gap * idx, 3)
        for idx, center in enumerate(unique)
    }
    return [normalized[round(value, 3)] for value in snapped]


def _stabilize_graph_layout(
    points: Sequence[tuple[float, float]],
    edges: Sequence[tuple[int, int]],
) -> tuple[list[tuple[float, float]], list[tuple[int, int]]]:
    if not points:
        return [], []

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    tolerance = max(2.5, span * 0.015)

    snapped_x = _regularize_uniform_axis(xs, tolerance)
    snapped_y = _regularize_uniform_axis(ys, tolerance)
    snapped_points = [(snapped_x[idx], snapped_y[idx]) for idx in range(len(points))]

    order = sorted(range(len(snapped_points)), key=lambda idx: (snapped_points[idx][1], snapped_points[idx][0], idx))
    remap = {old: new for new, old in enumerate(order)}
    stable_points = [snapped_points[idx] for idx in order]
    stable_edges = sorted({_edge_key(remap[a], remap[b]) for a, b in edges})
    return stable_points, stable_edges



def _graph_from_mask(mask: Sequence[Sequence[bool]]) -> tuple[list[tuple[float, float]], list[tuple[int, int]]]:

    key_pixels = [
        (row, col)
        for row in range(len(mask))
        for col in range(len(mask[0]))
        if mask[row][col] and _is_key_pixel(mask, row, col)
    ]
    if not key_pixels:
        key_pixels = _fallback_key_pixels(mask)
    if len(key_pixels) < 2:
        raise ValueError("草图中未识别出足够的道路节点，请提高对比度或降低阈值")

    node_components = _connected_components(key_pixels)
    node_positions: list[tuple[float, float]] = []
    cell_to_node: dict[tuple[int, int], int] = {}

    for node_id, comp in enumerate(node_components):
        rows = [item[0] for item in comp]
        cols = [item[1] for item in comp]
        center_row = (min(rows) + max(rows)) * 0.5
        center_col = (min(cols) + max(cols)) * 0.5
        node_positions.append((center_col, center_row))
        for cell in comp:
            cell_to_node[cell] = node_id


    visited_segments: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    edges: set[tuple[int, int]] = set()

    for node_id, comp in enumerate(node_components):
        for cell in comp:
            for neighbor in _dark_neighbors(mask, cell[0], cell[1]):
                if cell_to_node.get(neighbor) == node_id:
                    continue
                segment_key = _segment_key(cell, neighbor)

                if segment_key in visited_segments:
                    continue
                other_node, traversed = _trace_to_next_node(mask, cell_to_node, node_id, cell, neighbor)
                visited_segments.update(traversed)
                if other_node is None or other_node == node_id:
                    continue
                edges.add(_edge_key(node_id, other_node))


    if not edges:
        raise ValueError("草图中未识别出有效道路线段，请尝试更清晰的黑底/白底线稿")

    used_nodes = sorted({idx for edge in edges for idx in edge})
    remap = {old: new for new, old in enumerate(used_nodes)}
    compact_points = [node_positions[idx] for idx in used_nodes]
    compact_edges = sorted((remap[a], remap[b]) for a, b in edges if a in remap and b in remap)
    return _stabilize_graph_layout(compact_points, compact_edges)



def extract_layout_from_image(
    image_path: str,
    *,
    threshold: float,
    max_resolution: int,
    world_scale: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int]]]:
    mask, sampled_width, sampled_height = _load_image_mask(image_path, threshold, max_resolution)
    dark_count = sum(1 for row in mask for cell in row if cell)
    _layout_debug_log(
        f"extract start: image={bpy.path.abspath(image_path or '')} threshold={threshold:.3f} "
        f"max_resolution={max_resolution} world_scale={world_scale} sampled={sampled_width}x{sampled_height} dark_pixels={dark_count}"
    )

    extraction_errors: list[str] = []
    graph_points: list[tuple[float, float]] = []
    graph_edges: list[tuple[int, int]] = []
    used_stage = ""
    for candidate_mask, stage_name in ((_thin_mask(mask), "骨架细化"), (mask, "原始二值图")):
        try:
            graph_points, graph_edges = _graph_from_mask(candidate_mask)
            used_stage = stage_name
            break
        except ValueError as exc:
            extraction_errors.append(f"{stage_name}：{exc}")
    else:
        raise ValueError("；".join(extraction_errors) or "草图提取失败")

    _layout_debug_log(f"extract graph stage={used_stage}")
    _layout_debug_log(f"extract graph points(raw)={[(round(x, 3), round(y, 3)) for x, y in graph_points]}")
    _layout_debug_log(f"extract graph edges(raw)={[(int(a), int(b)) for a, b in graph_edges]}")

    xs = [point[0] for point in graph_points]

    ys = [point[1] for point in graph_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    center_x = (min_x + max_x) * 0.5
    center_y = (min_y + max_y) * 0.5
    factor = (2.0 * max(world_scale, 1.0)) / span

    points = [
        (
            round((x - center_x) * factor, 3),
            round((center_y - y) * factor, 3),
            0.0,
        )
        for x, y in graph_points
    ]
    edges = [(int(a), int(b)) for a, b in graph_edges]
    _debug_log_points("extract points(world)", points)
    _debug_log_edges("extract edges(world)", points, edges)
    return points, edges



class SCG_OT_fill_layout_demo(bpy.types.Operator):
    bl_idname = "scg.fill_layout_demo"
    bl_label = "载入示例布局"
    bl_description = (
        "填入单块矩形示例：4 角点 + 4 条边 → 1 个街区。"
        "尺寸对齐当前城市或默认 432×334m（整数），矩形中心在 3D 游标"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        width, depth = _demo_layout_footprint(context)
        cursor = context.scene.cursor.location
        cx = int(round(cursor.x))
        cy = int(round(cursor.y))
        cz = int(round(cursor.z))
        demo_points = _rectangle_points_centered(cx, cy, cz, width, depth)
        scene.scg_layout_points_json = _format_demo_layout_json(
            [[int(p[0]), int(p[1]), int(p[2])] for p in demo_points]
        )
        scene.scg_layout_edges_json = _format_demo_layout_json(_DEMO_EDGES)
        scene.scg_layout_create_boundary_face = False
        _set_layout_status(
            scene,
            f"布局控制已载入 {_DEMO_LAYOUT_NAME}：{len(demo_points)} 个点，"
            f"{len(_DEMO_EDGES)} 条边；{width}×{depth}m，中心在游标",
        )
        self.report({"INFO"}, scene.scg_layout_status)
        return {"FINISHED"}




class SCG_OT_apply_layout(bpy.types.Operator):
    bl_idname = "scg.apply_layout"
    bl_label = "应用布局"
    bl_description = "解析点集与边集，并重建 ICity Base 的道路布局"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.view_layer is not None

    def execute(self, context):
        scene = context.scene
        try:
            points, edges = parse_layout_inputs(
                scene.scg_layout_points_json,
                scene.scg_layout_edges_json,
            )
            ok, message = apply_layout_graph(context, scene, points, edges)
        except Exception as exc:
            message = str(exc)
            _set_layout_status(scene, f"布局应用失败：{message}")
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        _set_layout_status(scene, message)
        if ok:
            self.report({"INFO"}, message)
            return {"FINISHED"}

        self.report({"ERROR"}, message)
        return {"CANCELLED"}


class SCG_OT_extract_layout_from_image(bpy.types.Operator):
    bl_idname = "scg.extract_layout_from_image"
    bl_label = "草图提取布局"
    bl_description = "从草图图像中提取点线关系，并写回布局输入框"
    bl_options = {"REGISTER", "UNDO"}

    apply_immediately: bpy.props.BoolProperty(
        name="提取后立即应用",
        default=False,
        options={"SKIP_SAVE"},
    )



    @classmethod
    def poll(cls, context):
        return context.view_layer is not None

    def execute(self, context):
        scene = context.scene
        try:
            points, edges = extract_layout_from_image(
                scene.scg_layout_image_path,
                threshold=scene.scg_layout_image_threshold,
                max_resolution=scene.scg_layout_extract_resolution,
                world_scale=scene.scg_layout_world_scale,
            )
            center_on_cursor = getattr(scene, "scg_layout_center_on_cursor", True)
            points = _translate_layout_to_cursor(
                points,
                context.scene.cursor.location,
                enabled=center_on_cursor,
            )
            scene.scg_layout_points_json = _format_compact_json(points)
            scene.scg_layout_edges_json = _format_compact_json(edges)
            message = f"草图提取完成：{len(points)} 个点，{len(edges)} 条边"
            if center_on_cursor:
                message += "，点集已按 3D 游标居中"
            if self.apply_immediately:
                _ok, applied_message = apply_layout_graph(context, scene, points, edges)
                message = f"{message}；{applied_message}"
        except Exception as exc:
            _layout_debug_log(f"extract/apply exception: {exc}")
            _layout_debug_log(traceback.format_exc())
            message = str(exc)
            _set_layout_status(scene, f"草图提取失败：{message}")
            self.report({"ERROR"}, message)
            return {"CANCELLED"}



        _set_layout_status(scene, message)
        self.report({"INFO"}, message)
        return {"FINISHED"}


class SCG_OT_restore_base_city(bpy.types.Operator):
    bl_idname = "scg.restore_base_city"
    bl_label = "恢复基础城市"
    bl_description = (
        "从 ICity start.blend 还原默认道路网格，并按区域 1 参数重新生成基础城市"
        "（应用自定义布局后可一键回到稳定演示场景）"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return icity_scene_ready()

    def execute(self, context):
        scene = context.scene
        ok, message = restore_base_city_from_scene(scene, context)
        if ok:
            _set_layout_status(scene, message)
            self.report({"INFO"}, message)
            return {"FINISHED"}
        _set_layout_status(scene, f"恢复失败：{message}")
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


classes = (
    SCG_OT_fill_layout_demo,
    SCG_OT_apply_layout,
    SCG_OT_extract_layout_from_image,
    SCG_OT_restore_base_city,
)
