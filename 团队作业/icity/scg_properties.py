"""
Smart City Generator — Scene 自定义属性（阶段一 Day 2-3）。
"""

from __future__ import annotations

import bpy

_SCG_TYPE_ITEMS = (
    ("1", "类型1", "资产样式 1", 0),
    ("2", "类型2", "资产样式 2", 1),
)


def _scg_car_model_items(self, context):
    from .core.assets_manager import car_model_catalog

    items = []
    for idx, (model_id, label) in enumerate(car_model_catalog().items()):
        items.append((model_id, label, f"车辆模型：{label}", idx))
    if not items:
        items.append(("BMW", "BMW", "默认车辆（资产缺失时占位）", 0))
    return items


def register():
    bpy.types.Scene.scg_city_scale = bpy.props.EnumProperty(
        name="城市规模",
        description="小型：约一半地块为公园；中型：全部为程序化建筑区",
        items=(
            ("SMALL", "小型", "", 0),
            ("MEDIUM", "中型", "", 1),
        ),
        default="MEDIUM",
    )
    bpy.types.Scene.scg_building_density = bpy.props.EnumProperty(
        name="建筑密度",
        description="映射到 ICity 面 Attribute「Floor count / Floor count max」",
        items=(
            ("LOW", "低", "", 0),
            ("MEDIUM", "中", "", 1),
            ("HIGH", "高", "", 2),
        ),
        default="MEDIUM",
    )
    bpy.types.Scene.scg_building_type = bpy.props.EnumProperty(
        name="建筑样式",
        description="ICity 程序化建筑在 ICity_Procedural 中的索引",
        items=_SCG_TYPE_ITEMS,
        default="1",
    )
    bpy.types.Scene.scg_road_type = bpy.props.EnumProperty(
        name="道路类型",
        items=_SCG_TYPE_ITEMS,
        default="1",
    )
    bpy.types.Scene.scg_tree_type = bpy.props.EnumProperty(
        name="树木类型",
        items=_SCG_TYPE_ITEMS,
        default="1",
    )
    bpy.types.Scene.scg_bench_type = bpy.props.EnumProperty(
        name="座椅类型",
        items=_SCG_TYPE_ITEMS,
        default="1",
    )
    bpy.types.Scene.scg_enter_edit_after_generate = bpy.props.BoolProperty(
        name="生成后进入编辑",
        description="勾选后，生成基础城市完成时进入 Edit City（不勾选则保持 Object 模式，避免与 ICity Edit 切换冲突）",
        default=False,
    )
    bpy.types.Scene.scg_street_light_night = bpy.props.BoolProperty(
        name="路灯夜间发光",
        description="添加路灯时开启材质 Emission（模板1 night 联动预留）",
        default=False,
    )
    bpy.types.Scene.scg_template_id = bpy.props.IntProperty(
        name="模板编号",
        description="对应 config/templates.json 的键（0、1…）",
        default=0,
        min=0,
        max=99,
    )
    bpy.types.Scene.scg_layout_points_json = bpy.props.StringProperty(
        name="点集 JSON",
        description="支持 JSON 或 Python 列表/元组，例如 [[0,0,0],[200,0,0]]",
        default="[]",
    )
    bpy.types.Scene.scg_layout_edges_json = bpy.props.StringProperty(
        name="边集 JSON",
        description="支持 JSON 或 Python 列表/元组，例如 [[0,1],[1,2]]",
        default="[]",
    )
    bpy.types.Scene.scg_layout_image_path = bpy.props.StringProperty(
        name="草图图像",
        description="用于自动提取道路点线的草图图片路径",
        subtype="FILE_PATH",
        default="",
    )
    bpy.types.Scene.scg_layout_image_threshold = bpy.props.FloatProperty(
        name="草图阈值",
        description="亮度低于该阈值的像素会被视为道路草图",
        default=0.55,
        min=0.05,
        max=0.95,
    )
    bpy.types.Scene.scg_layout_extract_resolution = bpy.props.IntProperty(
        name="提取分辨率",
        description="草图提取时的最大采样边长，值越大越精细但越慢",
        default=96,
        min=32,
        max=256,
    )
    bpy.types.Scene.scg_layout_world_scale = bpy.props.FloatProperty(
        name="布局尺度",
        description="提取或应用布局后，在 Blender 世界中的整体尺寸范围",
        default=450.0,
        min=10.0,
        soft_max=2000.0,
    )
    bpy.types.Scene.scg_layout_create_boundary_face = bpy.props.BoolProperty(
        name="自动补边界面",
        description="根据点集凸包生成一个外边界面，便于 ICity 保留建筑区域",
        default=True,
    )
    bpy.types.Scene.scg_layout_center_on_cursor = bpy.props.BoolProperty(
        name="以游标为布局中心",
        description="应用布局时将点集几何中心平移到 3D 游标（XY），与生成基础城市居中观感一致",
        default=True,
    )
    bpy.types.Scene.scg_layout_status = bpy.props.StringProperty(
        name="布局状态",
        description="记录最近一次布局控制执行结果",
        default="尚未应用布局",
    )
    # 阶段三 A：动态元素参数（车辆/行人/动画在阶段 C 使用）
    bpy.types.Scene.scg_car_model = bpy.props.EnumProperty(
        name="车辆型号",
        description="添加车辆与行人时使用",
        items=_scg_car_model_items,
        default=0,
    )
    bpy.types.Scene.scg_car_count = bpy.props.IntProperty(
        name="车辆数量",
        description="一键添加时的车辆数量",
        default=2,
        min=0,
        max=10,
    )
    bpy.types.Scene.scg_pedestrian_count = bpy.props.IntProperty(
        name="行人数量",
        description="一键添加时的行人数量",
        default=3,
        min=0,
        max=20,
    )
    bpy.types.Scene.scg_boat_count = bpy.props.IntProperty(
        name="船只数量",
        description="湖面环绕行驶的船只数量（需先添加中央山水）",
        default=1,
        min=0,
        max=5,
    )
    bpy.types.Scene.scg_animation_frame_end = bpy.props.IntProperty(
        name="动画结束帧",
        description="路径动画帧范围 1 ~ 此值",
        default=120,
        min=24,
        max=500,
    )
    # 阶段四 P1：自然语言（区域 7）
    bpy.types.Scene.scg_nl_input_text = bpy.props.StringProperty(
        name="自然语言指令",
        description="输入中文指令，例如：将天色变暗、添加2辆车辆",
        default="",
    )
    bpy.types.Scene.scg_use_llm = bpy.props.BoolProperty(
        name="使用 LLM",
        description="开启后尝试调用大模型解析（P2）；关闭时使用离线规则",
        default=False,
    )
    from .scg_nl_preferences import PROVIDERS, on_nl_provider_change

    bpy.types.Scene.scg_nl_provider = bpy.props.EnumProperty(
        name="LLM 提供商",
        items=[
            ("VOLCENGINE", "火山引擎", ""),
            ("DEEPSEEK", "DeepSeek", ""),
            ("DASHSCOPE", "通义千问", ""),
            ("ZHIPU", "智谱 GLM", ""),
            ("OPENAI", "OpenAI", ""),
            ("CUSTOM", "自定义兼容接口", ""),
        ],
        default="DEEPSEEK",
        update=on_nl_provider_change,
    )
    bpy.types.Scene.scg_nl_api_key = bpy.props.StringProperty(
        name="API Key",
        description="OpenAI 兼容接口密钥；可点「保存到本地」持久化",
        default="",
        subtype="PASSWORD",
    )
    bpy.types.Scene.scg_nl_base_url = bpy.props.StringProperty(
        name="Base URL",
        default=PROVIDERS["DEEPSEEK"][0],
    )
    bpy.types.Scene.scg_nl_model = bpy.props.StringProperty(
        name="模型",
        default=PROVIDERS["DEEPSEEK"][1],
    )
    bpy.types.Scene.scg_nl_temperature = bpy.props.FloatProperty(
        name="Temperature",
        default=0.05,
        min=0.0,
        max=2.0,
    )
    bpy.types.Scene.scg_nl_debug = bpy.props.BoolProperty(
        name="NL 调试日志",
        default=False,
    )
    bpy.types.Scene.scg_nl_status = bpy.props.StringProperty(
        name="NL 执行状态",
        description="最近一次自然语言指令执行摘要",
        default="尚未执行",
    )
    bpy.types.Scene.scg_nl_last_reply = bpy.props.StringProperty(
        name="NL 回复",
        description="解析层返回的 reply 摘要",
        default="",
    )
    bpy.types.Scene.scg_nl_last_source = bpy.props.StringProperty(
        name="NL 解析来源",
        description="最近一次指令的解析方式：llm / offline_rule 等",
        default="",
    )


def unregister():
    for name in (
        "scg_city_scale",
        "scg_building_density",
        "scg_building_type",
        "scg_road_type",
        "scg_tree_type",
        "scg_bench_type",
        "scg_enter_edit_after_generate",
        "scg_street_light_night",
        "scg_template_id",
        "scg_layout_points_json",
        "scg_layout_edges_json",
        "scg_layout_image_path",
        "scg_layout_image_threshold",
        "scg_layout_extract_resolution",
        "scg_layout_world_scale",
        "scg_layout_create_boundary_face",
        "scg_layout_center_on_cursor",
        "scg_layout_status",
        "scg_car_model",
        "scg_car_count",
        "scg_pedestrian_count",
        "scg_boat_count",
        "scg_animation_frame_end",
        "scg_nl_input_text",
        "scg_use_llm",
        "scg_nl_provider",
        "scg_nl_api_key",
        "scg_nl_base_url",
        "scg_nl_model",
        "scg_nl_temperature",
        "scg_nl_debug",
        "scg_nl_status",
        "scg_nl_last_reply",
        "scg_nl_last_source",
    ):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
