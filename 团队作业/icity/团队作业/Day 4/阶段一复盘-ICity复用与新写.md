# 阶段一复盘：ICity 可复用 vs 必须新写

> 对应 `待办工作流程及时间线.md` §4.1.4「阶段复盘」。  
> Day 4 其余项（安装说明、全新 blend 自测、Git 与 B 对齐）团队按 **已完成/跳过** 处理；本文档集中记录阶段一的技术结论，供阶段二～五查阅。

**结论先行**：阶段一采用 **「ICity 引擎 + SCG 编排层」**——不重写几何节点与 Start 模板，用 **直接写 Attribute / 节点输入** 实现批量生成；用 **自选 Operator 刷新链** 替代「手动画线 + 逐面 Apply」。

---

## 1. 架构分层

```text
┌─────────────────────────────────────────────────────────┐
│  Smart City Generator（团队新写，scg_* / SCG_*）          │
│  Panel、Scene 属性、一键生成、模板/NL 占位                 │
└──────────────────────────┬──────────────────────────────┘
                           │ 调用 / 读写
┌──────────────────────────▼──────────────────────────────┐
│  ICity 原生（__init__.py，SNA_* / sna.*）               │
│  Start、几何节点、资产库、Edit 手编、City/Road Apply      │
└──────────────────────────┬──────────────────────────────┘
                           │ 依赖
┌──────────────────────────▼──────────────────────────────┐
│  数据与资源                                              │
│  ICity start.blend、Road 2 节点组、mesh Attribute、      │
│  assets/Assets/Default/*.blend、assets/team/（阶段二）   │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 阶段一已复用的 ICity 能力

### 2.1 直接调用的 Operator（`bpy.ops.sna.*`）

| bl_idname | 调用位置 | 用途 | 备注 |
|-----------|----------|------|------|
| `sna.start_5209e` | `city_generator.ensure_icity_started()`、`scg.start_icity` | 追加 `ICity start.blend`，初始化场景 | **必须复用**，勿自写 append 逻辑 |
| `sna.procedural_building_filter_05bed` | `_refresh_procedural_buildings()` | 按 Attribute 刷新程序化建筑 | 生成末尾调用 |
| `sna.park_filter_5a7a2` | 同上 | 刷新公园 | 小型城市含 Park 面时必要 |
| `sna.sync_city_76707` | 同上 | 刷新 `ICity_Procedural` 内对象 | 生成末尾调用 |
| `sna.light_city_20ca9` | `enter_icity_edit_mode()`（可选） | 进入 Edit 时更新灯光节点 | 非生成主路径 |

### 2.2 复用的 Blender 数据 API（不经过 Operator）

与 ICity 文档 §7「机制 2」一致，团队代码 **直接读写** 以下对象（Start 后必存在）：

| 目标 | API 用法 | 团队封装 |
|------|----------|----------|
| 面 Attribute | `mesh.attributes["space type"]` 等批量赋值 | `apply_mesh_city_attributes()` |
| 边 Attribute | `Road del` / `Tree` / `Bench` / `Light` | `apply_mesh_road_attributes()` |
| 道路节点组 | `bpy.data.node_groups["Road 2"].nodes["Tree"].inputs[4]` | `_apply_road_node_object()` |
| 道路材质 | `Road 2.nodes["Road"].inputs[2]` | `_apply_road_texture()`（团队 JPG） |
| 集合内模板物体 | `bpy.data.collections["ICity_Tree"].objects[i]` | `_object_from_collection()` |
| 场景枚举同步 | `scene.sna_procedural_building_browser` 等 | `_sync_icity_scene_props_for_ui()` |
| 视口刷新 | `update_tag`、`depsgraph.update`、3D 视口 `tag_redraw` | `_flush_viewport_refresh()` |

### 2.3 复用但做了「安全封装」的 ICity 行为

| ICity 原生 | 团队处理 | 原因 |
|------------|----------|------|
| `sna.edit_city_d7cab` | **生成流程不用**；改用 `enter_icity_edit_mode()` + `scg.edit_city` | 原生为 **toggle**，连点生成会进出 Edit |
| `sna.start_5209e` | `scg.start_icity` 包一层 + `icity_collection_exists()` 判断 | 面板 poll、避免重复 Start 对话框 |

### 2.4 阶段一未调用、但阶段二～五可能复用的 ICity Operator

| bl_idname | 典型用途 | 计划阶段 |
|-----------|----------|----------|
| `sna.append_assets_ffd74` | 从资产库追加 Bench/Tree/Light 等 | 二（或自写 append + 映射表） |
| `sna.read_97c87` / `sna.refresh_c6cb8` | 刷新 `All assets` 索引 | 二（若走完整资产浏览器） |
| `sna.road_apply_5c3ab` | 选中边 + 按名称设街道物件 | 二可选；当前用节点直写替代 |
| `sna.city_apply_dae66` | 选中面 + City apply | 一般不用于一键生成（需选面） |
| `sna.floor_count_min_c2cf8` 等 | 手调单层属性 | 已由批量写 Attribute 替代 |
| `sna.assign_road_deef9` | 手动画道路边 | 一键生成用写 `Road del=False` 替代 |
| `sna.light_city_20ca9` | 灯光/夜间 | 三（天气 day/night） |
| 公园/代理显隐类 `sna.hide_park_*` 等 | 视口优化 | 三～五按需 |

完整清单见 [icity简述.md](../../icity简述.md) §10。

---

## 3. 阶段一故意不用的 ICity 路径

| 能力 | 不用的原因 | 团队替代 |
|------|------------|----------|
| `sna.city_apply_dae66` | 依赖 Edit 模式 + **当前选中面** | 遍历全部面写 `space type` / `Procedural index` |
| `sna.road_apply_5c3ab` | 依赖选中边 + `sna_street_asset_browser` 单名 | 批量写边 Attribute + `Road 2` 节点 Object |
| `sna.edit_city_d7cab`（生成末尾） | toggle 破坏 Object 模式刷新 | 默认保持 Object；可选 `enter_icity_edit_mode` |
| ICity 资产缩略图浏览器 | 作业要简化参数（类型1/2） | 集合序号选取；阶段二可改为显式名称映射 |
| 修改 `__init__.py` 内 `SNA_*` 类 | 维护成本、合并冲突 | `scg_register` 外挂注册 |

---

## 4. 必须新写（团队 SCG 层）的内容

### 4.1 已新写（阶段一完成）

| 模块 | 职责 | 为何不能只用 ICity |
|------|------|-------------------|
| `scg_register.py` | 注册 properties / operators / ui | ICity 无团队入口 |
| `scg_properties.py` | `scg_city_scale` 等 Scene 属性 | 作业参数与 `sna_*` 分离 |
| `ui/panel_smart_city.py` | 独立 Panel、分区 1～6 | 不挤占 `SNA_PT_ICITY_EDITOR` |
| `operators/icity_bridge.py` | `scg.start_icity`、`scg.edit_city` | 安全封装与 poll |
| `operators/generate_base.py` | `scg.generate_base_city` | 一键编排无对应单一 sna op |
| `core/city_generator.py` | 批量 Attribute、节点、刷新链 | ICity 只有「选中元素 + Apply」 |
| `core/assets_manager.py` | `assets/team/` 路径映射 | 团队资产与 ICity 索引分离 |
| `__init__.py` 末尾 6 行 | `scg_register.register()` | 最小侵入挂钩 |

### 4.2 阶段二计划新写（在现有接口上扩展）

| 待实现 | 说明 | 与 ICity 关系 |
|--------|------|----------------|
| `resolve_street_object()` / append 助手 | 按名称或 team `.blend` 加载树/椅/灯 | 可复用 `wm.append` 模式，不必调 `append_assets` UI |
| `apply_template.py` | 读 `templates.json` → 写 `scg_*` → `generate_base_city_from_scene` | **复用** 阶段一生成核心 |
| 路灯 `add_street_lights()` | 沿道路实例化 | 新写；可参考 ICity Light 节点输入方式 |
| `assets_manager` 扩展映射表 | `TREE_OBJECTS`、`STREET_LIGHTS` 等 | 新写配置层 |

### 4.3 阶段三～五计划新写（占位已建）

| 文件 | 目标 | ICity 复用预期 |
|------|------|----------------|
| `operators/scene_enhance.py` | 天气、车流、灯光增强 | `light_city`、节点组 Boolean |
| `operators/layout_control.py` | 点/线布局 | 可能写 Attribute 或新集合 |
| `operators/nl_execute.py` + `command_executor.py` | JSON/NL → action | 内部调用 `generate_base_city`、模板、增强 op |
| `operators/render_output.py` | 渲染设置 | Blender 渲染 API 为主，少依赖 sna |

---

## 5. 对照表：作业能力 → 实现策略

| 作业能力（阶段一） | 实现策略 | 主要依赖 |
|--------------------|----------|----------|
| 插件可加载、Start | 复用 `sna.start_5209e` | ICity |
| 独立团队 Panel | 新写 `SCG_PT_*` | SCG |
| 一键基础城市 | 新写 `generate_base_city_from_scene` | ICity 数据 + 部分 sna 刷新 |
| 城市规模 / 密度 | 新写批量面 Attribute | ICity 几何节点读 Attribute |
| 树木/座椅类型1/2 | 新写节点 Object 引用 + 边开关 | `ICity_Tree` / `ICity_Bench` |
| 道路类型1/2 | 新写 `_apply_road_texture` | `assets/team`（阶段二补文件） |
| 手编精调 | 仍用 ICity Editor | `sna.edit_city`、`city_apply`、`road_apply` |

---

## 6. 风险与维护建议

1. **节点/Attribute 名称耦合**：`Road 2`、`space type` 等来自 `ICity start.blend`，ICity 大版本升级需回归测试。
2. **集合 Object 顺序**：类型1/2 = `objects[0/1]`，换模板后可能错位 → 阶段二改为显式名称映射（见 [资产机制说明.md](../Day%202-3/资产机制说明.md)）。
3. **`variables['sna_edit_city']`**：ICity 全局变量，团队 `enter_icity_edit_mode` 未同步该标志；仅用手编 Edit 时注意 ICity 面板状态可能不一致。
4. **勿复制 `__init__.py` 逻辑**：新功能进 `core/` / `operators/` / `ui/`，保持 `scg_register` 单入口。

---

## 7. 阶段二起推荐的调用原则

```text
能 bpy.ops.sna.start / sync / filter 刷新的 → 继续调用（少造轮子）
能直接写 Attribute / Road 2 节点的批量配置 → 在 city_generator 扩展
需要 UI 资产浏览器、按名 append 的 → 阶段二二选一：
    A) 扩展 assets_manager + 自 append（与 Smart City 面板一致）
    B) 调 sna.append_assets + 再 generate_base_city（与 ICity 工作流一致）
手编单面/单边精调 → 留给用户用 ICity Editor，SCG 不重复实现
```

---

## 8. 相关文档

| 文档 | 内容 |
|------|------|
| [Day 2-3/代码工作记录.md](../Day%202-3/代码工作记录.md) | 文件与调用链 |
| [Day 2-3/资产机制说明.md](../Day%202-3/资产机制说明.md) | 资产来源与类型1/2 |
| [icity简述.md](../../icity简述.md) §7–§12 | ICity 机制与 Operator 全集 |

---

*复盘日期：阶段一（M1）完成；Day 4 文档项按团队决策跳过，本文件作为 §4.1.4 产出。*
