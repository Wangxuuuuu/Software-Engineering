"""
团队新增 2D/3D 资产路径映射（阶段二 Day 5-6）。

团队道路主贴图（作业新增 2D 资产）：
  assets/team/textures/road_type1.jpg  → 道路类型1 BaseColor
  assets/team/textures/road_type2.jpg  → 道路类型2 BaseColor
存在上述文件时 **仅替换图片即可**，无需改代码。
不存在时回退 ICity 自带 PBR 贴图（开发/占位用）。
"""

from __future__ import annotations

import os
from typing import TypedDict

ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEAM_ASSETS_ROOT = os.path.join(ADDON_ROOT, "assets", "team")
TEAM_TEXTURES_DIR = os.path.join(TEAM_ASSETS_ROOT, "textures")

# 手动画车辆/行人路径库（用户自维护的 .blend，见 assets/manual_paths/README.md）
MANUAL_PATHS_DIR = os.path.join(ADDON_ROOT, "assets", "manual_paths")
MANUAL_PATHS_BLEND = os.path.join(MANUAL_PATHS_DIR, "manual_paths.blend")

ICITY_TEXTURES_DIR = os.path.join(ADDON_ROOT, "assets", "Assets", "Default", "textures")
ICITY_MATERIALS_BLEND = os.path.join(
    ADDON_ROOT, "assets", "Assets", "Default", "Road", "Materials.blend"
)

STREET_LIGHT_BLEND: str = os.path.join(TEAM_ASSETS_ROOT, "models", "lamp", "Street_Lamp.blend")
STREET_LAMP_TEXTURES_DIR: str = os.path.join(TEAM_ASSETS_ROOT, "models", "lamp", "Textures")
# append 后按文件名在此目录重连贴图（/fix 材质预览粉紫色）
STREET_LAMP_TEXTURE_SEARCH_DIRS: tuple[str, ...] = (
    STREET_LAMP_TEXTURES_DIR,
    os.path.join(TEAM_ASSETS_ROOT, "models", "lamp"),
)

# Street_Lamp.blend 内主 Object 名（与 .blend 内一致；换模型时只改 blend 内名称或此处）
STREET_LAMP_OBJECT_NAME: str = "Street_Lamp"
SCG_STREET_LAMP_OBJECT_NAME: str = "SCG_Team_Street_Lamp"

# 团队道路 BaseColor（作业「新增 2D 资产」放这里，固定文件名）
TEAM_ROAD_BASECOLOR: dict[int, str] = {
    1: os.path.join(TEAM_TEXTURES_DIR, "road_type1.jpg"),
    2: os.path.join(TEAM_TEXTURES_DIR, "road_type2.jpg"),
}


class RoadTextureSet(TypedDict, total=False):
    color: str | None
    normal: str | None
    roughness: str | None
    height: str | None
    icity_material: str | None
    label: str


def _tex(*parts: str) -> str:
    return os.path.join(*parts)


# 无 road_typeN.jpg 时的回退：模拟完整 PBR（Color + Normal + Roughness 等）
ICITY_PBR_FALLBACK: dict[int, RoadTextureSet] = {
    1: {
        "color": _tex(ICITY_TEXTURES_DIR, "Road 4 clean_BaseColor.jpg"),
        "normal": _tex(ICITY_TEXTURES_DIR, "Road 4 clean_Normal.jpg"),
        "roughness": _tex(ICITY_TEXTURES_DIR, "Road 4 clean_Roughness.jpg"),
        "icity_material": "ICity_Road 4 clean_Default",
        "label": "回退：ICity Road 4 clean（PBR）",
    },
    2: {
        "color": _tex(ICITY_TEXTURES_DIR, "Road 8 dirty_BaseColor.jpg"),
        "normal": _tex(ICITY_TEXTURES_DIR, "Road 8 dirty_Normal.jpg"),
        "roughness": _tex(ICITY_TEXTURES_DIR, "Road 8 dirty_Roughness.jpg"),
        "icity_material": "ICity_Road 8 dirty_Default",
        "label": "回退：ICity Road 8 dirty（PBR）",
    },
}


def _team_basecolor_set(type_id: int, path: str) -> RoadTextureSet:
    return {
        "color": path,
        "normal": None,
        "roughness": None,
        "height": None,
        "icity_material": None,
        "label": f"团队路面 类型{type_id}（road_type{type_id}.jpg · BaseColor）",
    }


def _resolve_road_set(type_id: int) -> RoadTextureSet:
    if type_id not in (1, 2):
        type_id = 1

    team_path = TEAM_ROAD_BASECOLOR.get(type_id)
    if team_path and os.path.isfile(team_path):
        return _team_basecolor_set(type_id, team_path)

    return dict(ICITY_PBR_FALLBACK.get(type_id, ICITY_PBR_FALLBACK[1]))  # type: ignore[return-value]


def road_texture_paths(texture_type: int) -> RoadTextureSet:
    return _resolve_road_set(texture_type)


def road_texture_path(texture_type: int) -> str:
    paths = road_texture_paths(texture_type)
    if paths.get("color"):
        return paths["color"]  # type: ignore[return-value]
    return TEAM_ROAD_BASECOLOR.get(texture_type, TEAM_ROAD_BASECOLOR[1])


def road_texture_available(texture_type: int) -> bool:
    paths = road_texture_paths(texture_type)
    if paths.get("color") and os.path.isfile(paths["color"]):
        return True
    mat_name = paths.get("icity_material")
    return bool(mat_name and os.path.isfile(ICITY_MATERIALS_BLEND))


def icity_road_material_name(texture_type: int) -> str | None:
    return road_texture_paths(texture_type).get("icity_material")


def road_texture_label(texture_type: int) -> str:
    return road_texture_paths(texture_type).get("label", f"类型{texture_type}")


def street_lamp_asset_available() -> bool:
    return os.path.isfile(STREET_LIGHT_BLEND)


# --- 阶段三：车辆 / 行人 / 船只 / 山水（lake）---

TEAM_MODELS_DIR = os.path.join(TEAM_ASSETS_ROOT, "models")
CARS_SOURCE_DIR = os.path.join(TEAM_MODELS_DIR, "cars", "source")
PEOPLE_BLEND = os.path.join(TEAM_MODELS_DIR, "people", "people.blend")
BOAT_BLEND = os.path.join(TEAM_MODELS_DIR, "boat", "boat_model_scarit.blend")
BOAT_OBJECT_NAME = "Boat"

LAKE_BLEND = os.path.join(
    TEAM_MODELS_DIR,
    "lake",
    "low-poly-tree-scene-free",
    "source",
    "LowPolyTrees.blend",
)
LAKE_TEXTURES_DIR = os.path.join(
    TEAM_MODELS_DIR,
    "lake",
    "low-poly-tree-scene-free",
    "textures",
)
LAKE_TEXTURE_SEARCH_DIRS: tuple[str, ...] = (
    LAKE_TEXTURES_DIR,
    os.path.join(TEAM_MODELS_DIR, "lake", "low-poly-tree-scene-free"),
)

# LowPolyTrees.blend 内集合：Terrain=水面+地面，Trees=山体树木
LAKE_TERRAIN_COLLECTION = "Terrain"
LAKE_TREES_COLLECTION = "Trees"

PEOPLE_BLEND_OBJECT_PREFIX = "Collection of people x 5"
PEOPLE_DEFAULT_OBJECT = "Collection of people x 5 04-001"

# 车辆 .blend 文件名（不含扩展名）→ 显示名
CAR_MODEL_FILES: dict[str, str] = {
    "BMW": "BMW",
    "Bugatti": "Bugatti",
    "Cyber Truck ": "Cyber Truck",
    "Dodge": "Dodge",
    "Ford": "Ford",
    "Mini": "Mini",
    "Porsche": "Porsche",
    "r34": "Nissan R34",
    "R35": "Nissan R35",
    "Supra": "Supra",
}


def _discover_car_models() -> dict[str, str]:
    """扫描 cars/source/*.blend，返回 {blend_stem: label}。"""
    found: dict[str, str] = {}
    if not os.path.isdir(CARS_SOURCE_DIR):
        return found
    for fn in sorted(os.listdir(CARS_SOURCE_DIR)):
        if not fn.lower().endswith(".blend"):
            continue
        stem = fn[:-6]
        label = CAR_MODEL_FILES.get(stem, stem.strip())
        found[stem] = label
    return found


def car_model_catalog() -> dict[str, str]:
    catalog = _discover_car_models()
    if catalog:
        return catalog
    return dict(CAR_MODEL_FILES)


def car_blend_path(model_id: str) -> str:
    return os.path.join(CARS_SOURCE_DIR, f"{model_id}.blend")


def car_texture_search_dirs(model_id: str, blend_path: str | None = None) -> tuple[str, ...]:
    """车辆贴图搜索目录（模型目录、共享 R35/textures、blend 同级路径）。"""
    dirs: list[str] = []
    candidates = [
        os.path.join(TEAM_MODELS_DIR, "cars", model_id, "textures"),
        os.path.join(TEAM_MODELS_DIR, "cars", model_id.strip(), "textures"),
        os.path.join(TEAM_MODELS_DIR, "cars", "textures"),
        os.path.join(TEAM_MODELS_DIR, "cars", "R35", "textures"),
        os.path.join(TEAM_MODELS_DIR, "cars", "source", "textures"),
        os.path.join(TEAM_MODELS_DIR, "cars"),
    ]
    if blend_path:
        blend_dir = os.path.dirname(blend_path)
        candidates.extend([
            blend_dir,
            os.path.join(blend_dir, "textures"),
            os.path.dirname(blend_dir),
            os.path.join(os.path.dirname(blend_dir), "textures"),
            os.path.join(os.path.dirname(blend_dir), "R35", "textures"),
        ])
    for sub in candidates:
        norm = os.path.normpath(sub)
        if os.path.isdir(norm) and norm not in dirs:
            dirs.append(norm)
    return tuple(dirs)


def car_model_available(model_id: str) -> bool:
    return os.path.isfile(car_blend_path(model_id))


def any_car_model_available() -> bool:
    return any(car_model_available(mid) for mid in car_model_catalog())


def people_asset_available() -> bool:
    return os.path.isfile(PEOPLE_BLEND)


def people_texture_search_dirs(blend_path: str | None = None) -> tuple[str, ...]:
    """行人贴图搜索目录（people/textures、blend 同级等）。"""
    dirs: list[str] = []
    candidates = [
        os.path.join(TEAM_MODELS_DIR, "people", "textures"),
        os.path.join(TEAM_MODELS_DIR, "people"),
        os.path.join(TEAM_MODELS_DIR, "textures"),
    ]
    if blend_path:
        blend_dir = os.path.dirname(blend_path)
        candidates.extend([
            blend_dir,
            os.path.join(blend_dir, "textures"),
            os.path.dirname(blend_dir),
            os.path.join(os.path.dirname(blend_dir), "textures"),
        ])
    for sub in candidates:
        norm = os.path.normpath(sub)
        if os.path.isdir(norm) and norm not in dirs:
            dirs.append(norm)
    return tuple(dirs)


def boat_asset_available() -> bool:
    return os.path.isfile(BOAT_BLEND)


def lake_landscape_asset_available() -> bool:
    return os.path.isfile(LAKE_BLEND)


def manual_paths_library_available() -> bool:
    return os.path.isfile(MANUAL_PATHS_BLEND)
