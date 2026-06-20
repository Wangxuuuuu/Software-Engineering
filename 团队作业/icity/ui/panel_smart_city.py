"""
Smart City Generator — 团队作业扩展面板（阶段一 Day 2）。

设计原则：
- 独立 Panel，不修改 SNA_PT_ICITY_EDITOR_6D34D。
- bl_category='ICity'，bl_order=5（位于 ICity editor / 链接面板之下）。
- UI 节奏与 ICity editor 对齐：未 Start 时仅 Start；Start 后才显示 Edit 与团队功能。
- 不包含 City·Road / 资产浏览器（留在 ICity editor）。
"""

from __future__ import annotations

import bpy

from ..core.assets_manager import (
    any_car_model_available,
    boat_asset_available,
    lake_landscape_asset_available,
    road_texture_available,
    road_texture_label,
    street_lamp_asset_available,
)
from ..core.city_generator import icity_collection_exists, icity_scene_ready

from ..core.template_manager import format_template_summary, get_template


def _draw_int_count_row(layout, scene, prop_name: str, label: str) -> None:
    """带 +/- 的数量行（避免 property_split 导致步进按钮失效）。"""
    row = layout.row(align=True)
    row.label(text=label)
    controls = row.row(align=True)
    controls.scale_x = 1.15
    minus = controls.operator("scg.adjust_dynamic_count", text="", icon="REMOVE")
    minus.prop_name = prop_name
    minus.delta = -1
    controls.prop(scene, prop_name, text="")
    plus = controls.operator("scg.adjust_dynamic_count", text="", icon="ADD")
    plus.prop_name = prop_name
    plus.delta = 1


class SCG_OT_placeholder_info(bpy.types.Operator):
    """阶段占位：确认团队作业面板已加载"""

    bl_idname = "scg.placeholder_info"
    bl_label = "团队作业模块已加载"
    bl_options = {"REGISTER"}

    def execute(self, context):
        self.report(
            {"INFO"},
            "Smart City Generator 已加载；请使用「生成基础城市」写入默认配置。",
        )
        return {"FINISHED"}


class SCG_PT_smart_city_generator(bpy.types.Panel):
    bl_label = "Smart City Generator"
    bl_idname = "SCG_PT_smart_city_generator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ICity"
    bl_order = 5
    # 默认展开，避免用户只看到 ICity 原生面板而找不到团队面板
    bl_options = set()

    @classmethod
    def poll(cls, context):
        return context.area is not None

    def draw(self, context):
        layout = self.layout
        ready = icity_scene_ready()

        # --- 场景状态 ---
        box = layout.box()
        box.label(text="场景状态", icon="INFO")
        if ready:
            box.label(text="ICity 已初始化，可使用下方功能", icon="CHECKMARK")
        elif icity_collection_exists():
            box.label(text="ICity 集合存在但缺少 ICity Base", icon="ERROR")
            box.label(text="请重新执行 Start", icon="BLANK1")
        else:
            box.label(text="尚未 Start，请先初始化场景", icon="ERROR")

        # --- ICity 基础（与 ICity editor 相同的显示节奏）---
        box = layout.box()
        box.label(text="ICity 基础", icon="PLUGIN")
        col = box.column(align=True)

        if not icity_collection_exists():
            # 未 Start：仅 Start（同 ICity editor 仅图标 + Start）
            col.operator("scg.start_icity", text="Start", icon="PLAY")
            col.label(text="Start 后解锁 Edit 与生成基础城市", icon="INFO")
        else:
            col.label(text="场景已加载", icon="CHECKMARK")
            row = col.row()
            row.enabled = ready
            row.operator("scg.edit_city", text="Edit City", icon="EDITMODE_HLT")
            if not ready:
                col.label(text="若 Edit 不可用，请重新 Start", icon="BLANK1")

        # --- 以下仅在 Start 完成后显示（不含 City·Road）---
        if not ready:
            box = layout.box()
            box.label(text="团队功能已锁定", icon="LOCKED")
            box.label(text="完成 Start 后显示模板 / 生成 / 渲染等", icon="BLANK1")
            layout.operator("scg.placeholder_info", text="检查模块状态", icon="QUESTION")
            return

        # --- [1] 基础场景生成（Day 2-3）---
        box = layout.box()
        box.label(text="1. 基础场景生成", icon="HOME")
        col = box.column(align=True)
        col.use_property_split = True
        scene = context.scene
        col.prop(scene, "scg_city_scale", text="城市规模")
        col.prop(scene, "scg_building_density", text="建筑密度")
        col.prop(scene, "scg_building_type", text="建筑样式")
        col.prop(scene, "scg_road_type", text="道路类型")
        col.prop(scene, "scg_tree_type", text="树木类型")
        col.prop(scene, "scg_bench_type", text="座椅类型")
        col.prop(
            scene,
            "scg_enter_edit_after_generate",
            text="生成后进入编辑",
        )
        col.separator()
        col.operator(
            "scg.generate_base_city",
            text="生成基础城市",
            icon="WORLD",
        )
        col.label(text="在 Object 模式写 Attribute 并刷新（不自动切换 Edit）", icon="INFO")
        col.label(text="参数旁圆点/菱形为 Blender 单选枚举样式", icon="BLANK1")

        # --- [2] 道路纹理（Day 5-6）---
        box = layout.box()
        box.label(text="2. 道路纹理", icon="TEXTURE")
        col = box.column(align=True)
        col.use_property_split = True
        col.prop(scene, "scg_road_type", text="道路类型")
        t1_ok = road_texture_available(1)
        t2_ok = road_texture_available(2)
        if t1_ok:
            col.label(text=f"类型1：{road_texture_label(1)}", icon="CHECKMARK")
        else:
            col.label(text="类型1：贴图缺失", icon="ERROR")
        if t2_ok:
            col.label(text=f"类型2：{road_texture_label(2)}", icon="CHECKMARK")
        else:
            col.label(text="类型2：贴图缺失", icon="ERROR")
        row = col.row(align=True)
        row.operator(
            "scg.apply_road_texture",
            text="应用道路纹理",
            icon="MATERIAL",
        )
        col.label(text="切换类型后点此或重新「生成基础城市」", icon="INFO")
        col.label(text="视口请用「材质预览」/「渲染」（非实体/纹理绘制）", icon="SHADING_RENDERED")

        # --- [3] 路灯（Day 6-7）---
        box = layout.box()
        box.label(text="3. 路灯（3D 资产）", icon="LIGHT")
        col = box.column(align=True)
        if street_lamp_asset_available():
            col.label(text="资产：lamp/Street_Lamp.blend", icon="CHECKMARK")
        else:
            col.label(text="缺少 Street_Lamp.blend", icon="ERROR")
        col.prop(scene, "scg_street_light_night", text="夜间 Emission")
        col.operator(
            "scg.apply_street_lights",
            text="添加路灯",
            icon="OUTLINER_OB_LIGHT",
        )
        col.label(text="需已生成道路；视口材质预览/渲染查看", icon="INFO")

        # --- [4] 模板（Day 7-8）---
        box = layout.box()
        box.label(text="4. 模版选择", icon="PRESET")
        col = box.column(align=True)
        col.use_property_split = True
        col.prop(scene, "scg_template_id", text="模板编号")
        tpl = get_template(scene.scg_template_id)
        if tpl:
            col.label(
                text=f"说明：{format_template_summary(str(scene.scg_template_id), tpl)}",
                icon="INFO",
            )
        else:
            col.label(text="模板不存在，请检查 templates.json", icon="ERROR")
        col.operator(
            "scg.apply_template",
            text="应用模板",
            icon="FILE_TICK",
        )
        col.label(text="一键：参数 + 环境 + 生成城市（ICity 默认路灯）", icon="BLANK1")

        # --- [5] 布局控制（阶段四）---
        box = layout.box()
        box.label(text="5. 布局控制", icon="MESH_GRID")
        col = box.column(align=True)
        col.label(text="手动点线输入（支持 JSON / Python 列表）", icon="EMPTY_AXIS")
        col.prop(scene, "scg_layout_points_json", text="点集 JSON")
        col.prop(scene, "scg_layout_edges_json", text="边集 JSON")
        col.prop(scene, "scg_layout_create_boundary_face", text="自动补边界面")
        col.prop(scene, "scg_layout_center_on_cursor", text="以游标为布局中心")
        row = col.row(align=True)
        row.operator("scg.fill_layout_demo", text="载入示例", icon="TEXT")
        row.operator("scg.apply_layout", text="应用布局", icon="CHECKMARK")
        col.operator(
            "scg.restore_base_city",
            text="恢复基础城市",
            icon="FILE_REFRESH",
        )
        col.label(text="应用自定义布局后，可一键还原默认道路并重新生成", icon="INFO")
        col.separator()
        col.label(text="草图布局控制（从图像提取点线）", icon="IMAGE_DATA")
        col.prop(scene, "scg_layout_image_path", text="草图图像")
        col.prop(scene, "scg_layout_image_threshold", text="提取阈值")
        col.prop(scene, "scg_layout_extract_resolution", text="提取分辨率")
        col.prop(scene, "scg_layout_world_scale", text="布局尺度")
        row = col.row(align=True)
        row.operator("scg.extract_layout_from_image", text="提取到输入框", icon="IMAGE_DATA")
        op = row.operator("scg.extract_layout_from_image", text="提取并应用", icon="CHECKMARK")
        op.apply_immediately = True
        col.separator()
        status_text = getattr(scene, "scg_layout_status", "尚未应用布局") or "尚未应用布局"
        col.label(text=f"状态：{status_text[:80]}", icon="INFO")
        col.label(text="道路图会重建到 ICity Base；City·Road 细节编辑仍在 ICity editor 中完成", icon="BLANK1")

        # --- [6] 场景增强 · 生态山水（阶段三 B）---
        box = layout.box()
        box.label(text="6. 场景增强（生态）", icon="WORLD")
        col = box.column(align=True)
        if lake_landscape_asset_available():
            col.label(text="山水资产：lake/LowPolyTrees.blend", icon="CHECKMARK")
        else:
            col.label(text="缺少 LowPolyTrees.blend", icon="ERROR")
        row = col.row(align=True)
        row.operator(
            "scg.add_landscape_surround",
            text="添加中央山水",
            icon="OUTLINER_OB_GROUP_INSTANCE",
        )
        col.operator(
            "scg.remove_landscape_surround",
            text="清除山水环境",
            icon="TRASH",
        )
        col.label(text="单块放大山水，城市位于水面中央（A8）", icon="INFO")
        col.label(text="添加后位置固定；失败残留会自动清理", icon="BLANK1")
        col.label(text="视口请用「材质预览」/「渲染」", icon="SHADING_RENDERED")

        col.separator()
        col.label(text="动态元素", icon="TIME")
        if any_car_model_available():
            col.prop(scene, "scg_car_model", text="车辆型号")
        else:
            col.label(text="车辆资产：cars/source 缺失", icon="ERROR")
        _draw_int_count_row(col, scene, "scg_car_count", "车辆数量")
        _draw_int_count_row(col, scene, "scg_pedestrian_count", "行人数量")
        col.operator(
            "scg.add_dynamic_elements",
            text="添加车辆与行人",
            icon="AUTO",
        )
        col.separator()
        col.label(text="湖面船只（优先手动画 SCG_Manual_Boat）", icon="MOD_OCEAN")
        _draw_int_count_row(col, scene, "scg_boat_count", "船只数量")
        if not boat_asset_available():
            col.label(text="船只资产：boat/boat_model_scarit.blend 缺失", icon="ERROR")
        col.operator(
            "scg.add_boats",
            text="添加船只",
            icon="MOD_OCEAN",
        )
        col.separator()
        col.label(text="手动画路径库", icon="CURVE_BEZCURVE")
        col.operator(
            "scg.export_manual_paths",
            text="保存曲线到路径库",
            icon="EXPORT",
        )
        col.label(text="含 SCG_Manual_Boat / Car / Ped → manual_paths.blend", icon="INFO")
        col.prop(scene, "scg_animation_frame_end", text="动画结束帧")
        col.label(text="车辆：双向机动车道靠右；优先 manual_paths.blend 路径库", icon="INFO")
        col.label(text="行人：里/外人行道自动偏移", icon="BLANK1")

        # --- [7] 自然语言（阶段四 P1 离线 / P2 LLM）---
        box = layout.box()
        box.label(text="7. 自然语言", icon="WORDWRAP_ON")
        col = box.column(align=True)
        col.enabled = ready
        row = col.row(align=True)
        row.label(text="指令输入", icon="TEXT")
        row.prop(scene, "scg_use_llm", text="LLM", toggle=True)
        if scene.scg_use_llm:
            from ..scg_nl_preferences import draw_nl_api_settings

            draw_nl_api_settings(col, scene)
            col.label(text="LLM 开启；API 失败时回退离线规则", icon="INFO")
        col.prop(scene, "scg_nl_input_text", text="")
        row_btn = col.row(align=True)
        row_btn.scale_y = 1.4
        row_btn.operator("scg.execute_nl", text="执行指令", icon="PLAY")
        status = getattr(scene, "scg_nl_status", "尚未执行") or "尚未执行"
        col.label(text=f"状态：{status[:120]}", icon="INFO")
        last_source = getattr(scene, "scg_nl_last_source", "") or ""
        if last_source == "llm":
            col.label(text="解析来源：LLM（DeepSeek 等大模型）", icon="WORLD")
        elif last_source == "offline_rule":
            col.label(text="解析来源：离线规则", icon="SCRIPT")
        elif last_source and "回退" not in status:
            col.label(text=f"解析来源：{last_source}", icon="QUESTION")
        tip = col.box()
        tip.scale_y = 0.85
        tip.label(text="离线示例（A6）：", icon="QUESTION")
        examples = (
            "将天色变暗",
            "将天色变为白天",
            "将道路改为类型 1",
            "应用模板 0",
            "将树木、道路和座椅均设为类型 1",
            "添加2辆车辆",
        )
        for ex in examples:
            tip.label(text=f"  · {ex}")

        # --- 占位：渲染输出 ---
        box = layout.box()
        box.label(text="8. 渲染输出", icon="RENDER_STILL")
        box.label(text="渲染成片在阶段五接入", icon="BLANK1")
        box.label(text="City·Road 请在 ICity editor 中操作", icon="OUTLINER_OB_MESH")

        layout.operator("scg.placeholder_info", text="检查模块状态", icon="QUESTION")


classes = (
    SCG_OT_placeholder_info,
    SCG_PT_smart_city_generator,
)
