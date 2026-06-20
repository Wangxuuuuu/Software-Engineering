# ICity Blender 插件简述

> 本文档用于《软件工程》课程，系统梳理 ICity 插件的项目目录、各部分作用、工作原理，以及 Python 与 Blender 的调用逻辑。  
> 插件版本：1.0.3 | 目标 Blender 版本：4.0.1+ | 源码路径：`scripts/addons/icity/`

---

## 目录

1. [项目概览](#1-项目概览)
2. [项目目录结构](#2-项目目录结构)
3. [源码组织特点](#3-源码组织特点)
4. [与 Blender 的集成方式](#4-与-blender-的集成方式)
5. [核心架构与工作原理](#5-核心架构与工作原理)
6. [典型工作流程](#6-典型工作流程)
7. [Python 修改物体/外观参数的四种机制](#7-python-修改物体外观参数的四种机制)
8. [网格 Attribute 完整对照表](#8-网格-attribute-完整对照表)
9. [Python 调用链示例](#9-python-调用链示例)
10. [主要模块与类清单](#10-主要模块与类清单)
11. [全局状态变量说明](#11-全局状态变量说明)
12. [资产库与索引机制](#12-资产库与索引机制)
13. [test.py 说明](#13-testpy-说明)
14. [最小可运行 Python 示例](#14-最小可运行-python-示例)
15. [课程分析要点](#15-课程分析要点)
16. [附录：关键代码片段索引](#16-附录关键代码片段索引)

---

## 1. 项目概览

**ICity** 是一款 Blender 插件，用于**程序化生成 3D 城市道路、建筑与景观**。

### 1.1 核心设计思想

插件采用「三层分离」架构：

| 层次 | 技术 | 职责 |
|------|------|------|
| **控制层** | Python（`__init__.py`） | UI 面板、按钮操作、参数写入、资产浏览、场景初始化 |
| **引擎层** | Geometry Nodes（几何节点） | 读取 Attribute / 节点输入，实际生成道路、建筑、景观 |
| **数据层** | 外部 `.blend` 资产库 | 预设建筑、公园、道路配件、材质、贴图 |

**关键结论**：Python **不直接建模**，而是向 `ICity Base` 网格的 **Attribute（属性）** 和几何节点 **Modifier 的输入** 写入参数，由节点图驱动最终城市生成。

### 1.2 bl_info 元信息

```python
bl_info = {
    "name"        : "ICity",
    "author"      : "ICity",
    "description" : "一款可以生成3D城市道路建筑景观的blender插件",
    "blender"     : (4, 0, 1),
    "version"     : (1, 0, 3),
    "category"    : "3D View",
    "warning"     : "Beta version!",
}
```

---

## 2. 项目目录结构

```
icity/
├── __init__.py              # 主程序（全部逻辑，约 3500 行）
├── test.py                  # 课程/实验脚本：用 BMesh 直接编辑 ICity Base 网格
├── ui.py                    # 空文件（预留，当前未使用）
├── icity简述.md             # 本文档
├── assets/                  # 核心资源目录
│   ├── ICity start.blend           # 启动模板（几何节点、集合、基础对象）
│   ├── Default building Procedural.png
│   ├── New Project (26).png        # UI Logo
│   ├── 16e8992ffebf47daba61aa6815a7177b (1).png  # 默认预览图
│   ├── Assets/
│   │   └── Default/                # 默认主题资产库
│   │       ├── All assets          # 资产索引清单（文本）
│   │       ├── All materials       # 材质索引清单（文本）
│   │       ├── Procedural/         # 程序化建筑 .blend
│   │       ├── Park/               # 公园 .blend
│   │       ├── Building presets/   # 预设建筑 .blend
│   │       ├── Building landscape/ # 景观 .blend
│   │       ├── Road/               # 道路配件 .blend
│   │       └── textures/           # 主题贴图
│   ├── icons/                      # UI 预览占位图标
│   │   ├── Custom asset.png
│   │   ├── Custom collection.png
│   │   └── Custom material.png
│   └── textures/                   # 全局贴图资源（道路、草地、树木等）
├── .idea/                   # PyCharm/IDEA 配置（非插件功能）
├── .vscode/                 # VS Code 配置（非插件功能）
└── __pycache__/             # Python 编译缓存
```

### 2.1 各路径作用详解

| 路径 | 作用 |
|------|------|
| `__init__.py` | 插件唯一入口：注册 UI、Operator、Scene 属性、事件处理器、快捷键 |
| `assets/ICity start.blend` | 用户点击 **Start** 后追加到当前场景的「城市引擎」模板 |
| `assets/Assets/Default/` | 可追加的建筑/道路/材质库根目录，可按主题扩展（如 Chicago） |
| `assets/Assets/Default/All assets` | 文本格式的资产索引，记录名称、类型、`.blend` 路径 |
| `assets/Assets/Default/All materials` | 文本格式的材质索引 |
| `assets/textures/` | 道路、草地、树叶、金属等 PBR 贴图 |
| `test.py` | 独立实验脚本，演示 BMesh 底层 API 编辑城市边界网格 |
| `ui.py` | 空文件，可能为后续模块化预留 |

---

## 3. 源码组织特点

### 3.1 单文件 monolith 架构

几乎全部逻辑集中在 `__init__.py` 一个文件中，包含：

- 40+ 个 Operator（操作类）
- 3 个 Panel（面板）
- 3 个 Menu（菜单）
- 1 个 AddonPreferences（偏好设置）
- 大量辅助函数与全局变量

### 3.2 可视化脚本生成痕迹

类名带有 **`SNA_` 前缀** 和 **哈希后缀**，例如：

- `SNA_OT_City_Apply_Dae66`（Operator）
- `SNA_PT_ICITY_EDITOR_6D34D`（Panel）
- `SNA_MT_89AD5`（Menu）

辅助函数也大量重复，如 `sna_set_active_attribute_572EC_5001C`、`sna_set_active_attribute_572EC_A11A7` 等，逻辑相同仅后缀不同。

**推断**：源码很可能由 **Serpens** 等 Blender 可视化脚本工具自动生成，而非手写模块化代码。这对软件工程分析有重要意义：开发效率高，但可维护性、可测试性较差。

### 3.3 命名约定

| 前缀/模式 | 含义 |
|-----------|------|
| `SNA_OT_` | Operator（操作） |
| `SNA_PT_` | Panel（面板） |
| `SNA_MT_` | Menu（菜单） |
| `sna_` | 函数、属性、变量前缀 |
| `bl_idname = "sna.xxx"` | Operator 在 Blender 中的调用 ID |

---

## 4. 与 Blender 的集成方式

### 4.1 插件生命周期

Blender 在「编辑 → 偏好设置 → 插件」中启用 ICity 时：

```
加载 icity 包
  → 执行 __init__.py
  → 调用 register()
      → 注册 Scene/Object/Material 自定义属性
      → bpy.utils.register_class(...) 注册所有 Operator/Panel
      → bpy.app.handlers.depsgraph_update_pre.append(...) 注册事件监听
      → 注册快捷键 Shift+M
```

禁用插件时调用 `unregister()`，逆序清理上述注册项。

### 4.2 使用的 Blender Python API 一览

| API | 用途 | 示例 |
|-----|------|------|
| `bpy.types.Operator` | 按钮触发的操作 | Start、City apply、Road apply |
| `bpy.types.Panel` | 3D 视图侧边栏 UI | `SNA_PT_ICITY_EDITOR_6D34D` |
| `bpy.types.AddonPreferences` | 插件偏好设置 | 自定义资产路径 |
| `bpy.props.EnumProperty` 等 | 场景/对象自定义属性 | `sna_citystreet`、`sna_city_space_type` |
| `bpy.ops.wm.append` | 从 `.blend` 追加数据 | 追加 Collection/Object/Material |
| `bpy.ops.mesh.attribute_set` | 写入网格 Attribute | 给选中面/边赋城市/道路参数 |
| `bpy.ops.object.mode_set` | 切换 OBJECT/EDIT 模式 | Edit city 进入编辑 |
| `bpy.app.handlers` | 持久事件回调 | 检测是否在 Edit city 模式 |
| `bpy.utils.previews` | 加载预览图标 | 资产浏览器缩略图 |
| `bpy.data.libraries.load` | 读取 `.blend` 内容列表 | 扫描资产库 |
| `bpy.data.node_groups` | 访问节点组 | 修改 Road 2、Spaces 等节点输入 |
| `obj.update_tag(refresh=...)` | 标记对象需刷新 | 触发几何节点重算 |

### 4.3 注册的 Scene 属性（部分）

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `sna_citystreet` | Enum | 主模式：`City` / `Road` |
| `sna_city_space_type` | Enum | 城市空间类型：`Procedural` / `Park` / `Presets` |
| `sna_street_asset_type` | Enum | 街道资产类型：Light、Bench、Tree、Texture 等 |
| `sna_procedural_building_browser` | Enum | 程序化建筑浏览器（带预览图） |
| `sna_building_presets_browser` | Enum | 预设建筑浏览器 |
| `sna_park_browser` | Enum | 公园浏览器 |
| `sna_landscape_browser` | Enum | 景观浏览器 |
| `sna_road_materials_browser` | Enum | 道路材质浏览器 |
| `sna_street_asset_browser` | Enum | 街道物件浏览器 |
| `sna_theme` | Enum (FLAG) | 主题过滤：All / General / Chicago |
| `sna_proxy_mode` | Bool | 代理模式（低模显示） |
| `sna_light_mode` | Bool | 灯光模式 |

### 4.4 注册的对象级属性

| 属性 | 挂载类型 | 说明 |
|------|----------|------|
| `sna_asset_category_path_object` | Object | 记录资产来源 `.blend` 路径 |
| `sna_asset_category_path_collection` | Collection | 同上（集合） |
| `sna_asset_category_path_material` | Material | 同上（材质） |

### 4.5 事件处理器（Handler）

```python
@persistent
def depsgraph_update_pre_handler_361D3(dummy):
    # 检测是否处于「编辑 ICity Base」模式
    variables['sna_edit_city'] = (
        bpy.context.mode == 'EDIT_MESH'
        and bpy.context.view_layer.objects.active.name == 'ICity Base'
    )

@persistent
def depsgraph_update_pre_handler_59166(dummy):
    # 缓存当前活动对象的 Attribute 名称列表
    list_0_6a49a = sna_store_atrributes_list_D7786_6A49A()
```

### 4.6 快捷键

- **Shift + M**：打开 ICity 插件偏好设置（`sna.open_addon_prefrences_34afe`）

---

## 5. 核心 **核心架构与工作原理**

### 5.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Python 控制层                           │
│  ┌──────────┐   ┌────────────┐   ┌─────────────────────┐   │
│  │ ICity    │   │ Operators  │   │ 全局变量             │   │
│  │ Editor   │──▶│ (40+ 个)   │──▶│ append / variables  │   │
│  │ Panel    │   └────────────┘   └─────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │ attribute_set / 修改 node inputs / wm.append
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Blender 场景（引擎层）                     │
│                                                              │
│  ICity Base ──Attribute──▶ ICity Spces (Geometry Nodes)     │
│  (面=城市区)                  │                              │
│  (边=道路)                    ▼                              │
│       │              ICity_Procedural / Presets / Park      │
│       │                                                      │
│       └────Attribute──▶ ICity Road (Geometry Nodes)          │
│                              │                               │
│                              ▼                               │
│                     道路 / 路灯 / 长椅 / 材质实例化           │
└──────────────────────────┬──────────────────────────────────┘
                           │ wm.append
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      数据层（资产库）                         │
│  assets/Assets/Default/*.blend  +  All assets 索引文件       │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 场景中的核心对象

Start 初始化后，场景中会出现以下关键对象/集合：

| 名称 | 类型 | 作用 |
|------|------|------|
| `ICity` | Collection | 根集合 |
| `ICity Base` | Mesh Object | **用户编辑的主网格**，面存城市参数，边存道路参数 |
| `ICity Road` | Mesh Object | 道路几何节点对象，含 `Road 2` 等节点组 |
| `ICity Road Boundry` | Object | 道路边界（不可选） |
| `ICity Spces` | Object | 城市空间生成器（不可选） |
| `ICity Procedural ground` | Object | 程序化地面（不可选） |
| `ICity building procedural base` | Object | 程序化建筑基座（不可选） |
| `Procedural building_Default_ICity` | Object | 默认程序化建筑模板（不可选） |
| `ICity Assets` | Collection | 隐藏资产集合（视口/渲染均隐藏） |
| `ICity_Procedural` | Collection | 已加载的程序化建筑实例 |
| `ICity_Presets` | Collection | 已加载的预设建筑 |
| `ICity_Park` | Collection | 已加载的公园 |
| `ICity_Light` / `ICity_Bench` / `ICity_Tree` 等 | Collection | 各类街道资产分类存放 |

### 5.3 数据存储规则（UI 提示）

- **City 模式**：`City attributes are stored on faces!`（城市属性存在**面**上）
- **Road 模式**：`Road attributes are stored on edges!`（道路属性存在**边**上）

---

## 6. 典型工作流程

### 6.1 完整流程概览

```
1. 启用插件
2. 侧边栏 ICity → Start（追加 ICity start.blend）
3. Edit city（进入 ICity Base 编辑模式）
4. 选择 City 或 Road 模式
5. 在 3D 视口中选择面（City）或边（Road）
6. 在面板中选择建筑/道路/资产类型
7. 点击 Assign / Apply 写入 Attribute 或节点参数
8. Geometry Nodes 自动重算，生成最终城市
9. （可选）Append Assets 追加更多外部资产
10. （可选）Sync city 刷新程序化建筑
```

### 6.2 步骤详解

#### 步骤 1：Start — 初始化场景

**Operator**：`SNA_OT_Start_5209E`（`sna.start_5209e`）

```python
# 从 ICity start.blend 追加 ICity 集合
bpy.ops.wm.append(
    directory=.../assets/ICity start.blend\Collection,
    filename='ICity',
    link=False
)
# 隐藏资产集合，锁定系统对象
bpy.data.collections['ICity Assets'].hide_viewport = True
bpy.data.collections['ICity Assets'].hide_render = True
bpy.context.view_layer.objects.active = bpy.data.objects['ICity Base']
bpy.data.objects['ICity Road'].hide_select = True
# ... 更多系统对象 hide_select = True
```

#### 步骤 2：Edit city — 进入/退出编辑模式

**Operator**：`SNA_OT_Edit_City_D7Cab`（`sna.edit_city_d7cab`）

- 激活 `ICity Base`
- 若已在 EDIT 模式则切回 OBJECT，否则进入 EDIT
- 调用 `sna.light_city_20ca9` 更新灯光状态

#### 步骤 3：City 模式 — 给面分配建筑

**Operator**：`SNA_OT_City_Apply_Dae66`（`sna.city_apply_dae66`）

**前置条件**：`variables['sna_edit_city'] == True`（必须在 Edit city 模式）

流程：
1. 激活 Attribute `space type`，写入类型码（0/1/2/3）
2. 根据 `sna_city_space_type` 写入对应索引 Attribute
3. 调用 `update_tag` 触发几何节点刷新

#### 步骤 4：Road 模式 — 给边分配道路属性

**Operator**：`SNA_OT_Road_Apply_5C3Ab`（`sna.road_apply_5c3ab`）

两种路径：
- **Texture 类型**：直接改 `Road 2` 节点组的材质输入
- **其他类型**：写边 Attribute 或改节点 Object/Collection 引用

#### 步骤 5：Append Assets — 追加外部资产

**Operator**：`SNA_OT_Append_Assets_Ffd74`（`sna.append_assets_ffd74`）

根据当前模式（City/Road）和资产类型，从对应 `.blend` 文件追加 Object/Collection/Material，并移动到正确的 ICity 集合中。

---

## 7. Python 修改物体/外观参数的四种机制

### 机制 1：网格 Attribute（最主要）

**原理**：`ICity Base` 预定义多种 Attribute，Python 切换「当前活动 Attribute」后，对选中的面/边写入值；Geometry Nodes 读取这些 Attribute 驱动生成。

**标准三步写法**：

```python
# 1. 缓存 Attribute 名称列表（由 Handler 自动维护，也可手动调用）
variables['sna_attributes'] = [attr.name for attr in obj.data.attributes]

# 2. 激活指定 Attribute
obj.data.attributes.active_index = variables['sna_attributes'].index('space type')

# 3. 对当前选中的面/边写入值（需在 EDIT_MESH 模式）
bpy.ops.mesh.attribute_set(value_int=1)      # 整数
bpy.ops.mesh.attribute_set(value_bool=True)  # 布尔
bpy.ops.mesh.attribute_set('INVOKE_DEFAULT') # 弹出对话框让用户输入
```

**封装函数**（插件内大量重复）：

```python
def sna_set_active_attribute_572EC_5001C(Name):
    bpy.context.active_object.data.attributes.active_index = \
        variables['sna_attributes'].index(
            bpy.context.active_object.data.attributes[Name].name
        )
```

### 机制 2：直接修改 Geometry Nodes 输入

对 `ICity Road`、`ICity Spces` 等对象，Python 直接读写节点组输入：

```python
# 道路材质
bpy.data.node_groups['Road 2'].nodes['Road'].inputs[2].default_value = material

# 街道物件（路灯、长椅等）
bpy.data.node_groups['Road 2'].nodes['Light'].inputs[4].default_value = obj

# 服务/瑕疵集合
bpy.data.node_groups['Road 2'].nodes['Services'].inputs[5].default_value = collection

# 通过 Modifier 接口访问（UI 面板用法）
modifier = bpy.data.objects['ICity Road'].modifiers['GeometryNodes']
input_id = modifier.node_group.interface.items_tree['All V'].identifier
modifier[input_id] = True

# 触发刷新
bpy.data.objects['ICity Road'].update_tag(refresh={'DATA'})
```

**公园/景观显隐控制**（遍历集合内所有带 NODES 修改器的对象）：

```python
modifier[input_name] = hide_assets['sna_show_grass_v_park']
obj.update_tag(refresh={'OBJECT', 'DATA'})
```

### 机制 3：追加/删除外部资产

```python
# 追加材质
before = list(bpy.data.materials)
bpy.ops.wm.append(
    directory=blend_path + r'\Material',
    filename='MaterialName',
    link=False
)
new_mat = [m for m in bpy.data.materials if m not in before][0]

# 追加对象并移动到指定集合
before = list(bpy.data.objects)
bpy.ops.wm.append(directory=blend_path + r'\Object', filename='Light1', link=False)
new_obj = [o for o in bpy.data.objects if o not in before][0]
sna_move_to_collection(True, new_obj, None, bpy.data.collections['ICity_Light'])

# 删除资产
bpy.data.objects['AssetName'].select_set(True)
bpy.ops.object.delete(confirm=True)
# 或
bpy.data.materials.remove(material=mat)
```

### 机制 4：全局开关（Proxy / Light Mode）

```python
# Proxy mode：低模代理显示，减轻视口负担
bpy.data.node_groups['Hide viewport input'].nodes['Proxy buildings'].inputs[0].default_value = proxy_on
bpy.data.node_groups['ICity Proxy'].nodes['Light'].inputs[0].default_value = proxy_on

# Light mode：控制城市灯光
bpy.data.node_groups['Light mode'].nodes['Boolean Math.003'].inputs[0].default_value = \
    (edit_city_mode and light_mode_enabled)
```

---

## 8. 网格 Attribute 完整对照表

### 8.1 面（Face）Attribute — City 模式

| Attribute 名 | 数据类型 | 含义 | 相关 Operator |
|-------------|----------|------|---------------|
| `space type` | INT | 0=Procedural, 1=Park, 2=Presets, 3=Custom | City apply |
| `Procedural index` | INT | 程序化建筑样式索引 | City apply |
| `Park` | INT | 公园样式索引 | City apply |
| `Presets` | INT | 预设建筑索引 | City apply |
| `Landscape` | INT | 景观索引（Presets 模式） | City apply |
| `Floor count` | INT/FLOAT | 最小楼层数 | Floor count min |
| `Floor count max` | INT/FLOAT | 最大楼层数 | Floor count max |
| `Offset x` | FLOAT | X 偏移 | Offset x |
| `Offset y` | FLOAT | Y 偏移 | Offset y |
| `Rotation z` | FLOAT | Z 轴旋转 | Rotation z |
| `Offset x preset` | FLOAT | 预设模式 X 偏移 | Offset x preset |
| `Offset y preset` | FLOAT | 预设模式 Y 偏移 | Offset y preset |
| `Rotation z preset` | FLOAT | 预设模式 Z 旋转 | Rotation z preset |

### 8.2 边（Edge）Attribute — Road 模式

| Attribute 名 | 数据类型 | 含义 | 相关 Operator |
|-------------|----------|------|---------------|
| `Road del` | BOOL | False=是道路, True=非道路 | Assign road / Remove road |
| `street type` | INT | 街道类型 | Set side count |
| `Road lanes width` | FLOAT | 车道宽度 | Road lanes width |
| `side walk offset` | FLOAT | 人行道宽度 | Sidewalk width |
| `crosswalk offset` | FLOAT | 人行横道偏移 | Crosswalk offset |
| `Light` / `Bench` / `Tree` 等 | BOOL | 各街道资产开关 | Road apply / Road remove |
| `Intersection offset` | FLOAT | 交叉口偏移 | Intersection offset |

### 8.3 space type 编码

| 值 | 枚举名 | 说明 |
|----|--------|------|
| 0 | Procedural | 程序化生成建筑 |
| 1 | Park | 公园 |
| 2 | Presets | 预设建筑 + 景观 |
| 3 | Custom | 自定义（预留） |

---

## 9. Python 调用链示例

### 9.1 用户分配程序化建筑（City Apply）

```
用户在 3D 视口选中 ICity Base 的面
  │
  ▼
UI 面板：选择 Procedural + 某建筑样式
  │
  ▼
点击 Assign → bpy.ops.sna.city_apply_dae66()
  │
  ├─ sna_set_active_attribute('space type')
  ├─ bpy.ops.mesh.attribute_set(value_int=0)    # Procedural
  │
  ├─ sna_set_active_attribute('Procedural index')
  ├─ bpy.ops.mesh.attribute_set(value_int=N)    # 建筑索引
  │
  └─ bpy.data.objects[building_name].update_tag(refresh={'DATA'})
       │
       ▼
  Geometry Nodes 读取 Attribute → 在对应面区域实例化建筑
```

### 9.2 用户分配道路材质（Road Apply - Texture）

```
用户选中 ICity Base 的边
  │
  ▼
UI：Street asset type = Texture，选择材质
  │
  ▼
点击 Apply → bpy.ops.sna.road_apply_5c3ab()
  │
  ├─ bpy.data.node_groups['Road 2'].nodes['Road'].inputs[2].default_value = mat
  └─ bpy.data.objects['ICity Road'].update_tag(refresh={'DATA'})
       │
       ▼
  道路几何节点应用新材质
```

### 9.3 用户追加路灯资产（Append Assets）

```
UI：city-street append = Road，street asset type = Light
  │
  ▼
选择资产 → bpy.ops.sna.append_assets_ffd74()
  │
  ├─ 从 append['sna_road_assets_filtered'] 查找匹配项
  ├─ bpy.ops.wm.append(directory=blend\Object, filename='Light1_...')
  ├─ 设置 appended_obj.sna_asset_category_path_object = blend_path
  └─ sna_move_to_collection(..., bpy.data.collections['ICity_Light'])
       │
       ▼
  新路灯对象可在 Road Apply 时分配给边
```

### 9.4 Edit city 模式检测

```
每帧 depsgraph 更新前
  │
  ▼
depsgraph_update_pre_handler_361D3()
  │
  └─ variables['sna_edit_city'] = (
         context.mode == 'EDIT_MESH'
         and active_object.name == 'ICity Base'
     )
       │
       ▼
  UI 面板根据 sna_edit_city 启用/禁用 City/Road 操作按钮
```

---

## 10. 主要模块与类清单

### 10.1 初始化与场景管理

| 类名 | bl_idname | 功能 |
|------|-----------|------|
| `SNA_OT_Start_5209E` | `sna.start_5209e` | 追加启动模板，初始化场景 |
| `SNA_OT_Edit_City_D7Cab` | `sna.edit_city_d7cab` | 进入/退出 ICity Base 编辑模式 |
| `SNA_OT_Sync_City_76707` | `sna.sync_city_76707` | 刷新 ICity_Procedural 集合内所有对象 |
| `SNA_OT_Light_City_20Ca9` | `sna.light_city_20ca9` | 更新灯光模式节点 |

### 10.2 城市编辑（City）

| 类名 | bl_idname | 功能 |
|------|-----------|------|
| `SNA_OT_City_Apply_Dae66` | `sna.city_apply_dae66` | 给选中面分配城市空间类型与建筑 |
| `SNA_OT_Floor_Count_Min_C2Cf8` | `sna.floor_count_min_c2cf8` | 设置最小楼层 |
| `SNA_OT_Floor_Count_Max_Db555` | `sna.floor_count_max_db555` | 设置最大楼层 |
| `SNA_OT_Offset_X_A87Eb` | `sna.offset_x_a87eb` | 面 X 偏移 |
| `SNA_OT_Offset_Y_45B11` | `sna.offset_y_45b11` | 面 Y 偏移 |
| `SNA_OT_Rotation_Z_4Edcd` | `sna.rotation_z_4edcd` | 面 Z 旋转 |
| `SNA_OT_Offset_X_Preset_5A427` | `sna.offset_x_preset_5a427` | 预设 X 偏移 |
| `SNA_OT_Offset_Y_Preset_Dcad4` | `sna.offset_y_preset_dcad4` | 预设 Y 偏移 |
| `SNA_OT_Rotation_Z_Preset_60648` | `sna.rotation_z_preset_60648` | 预设 Z 旋转 |
| `SNA_OT_Delete_From_Scene_City_324Ff` | `sna.delete_from_scene_city_324ff` | 从场景删除城市资产 |

### 10.3 道路编辑（Road）

| 类名 | bl_idname | 功能 |
|------|-----------|------|
| `SNA_OT_Road_Apply_5C3Ab` | `sna.road_apply_5c3ab` | 给选中边应用道路/街道资产 |
| `SNA_OT_Road_Remove_Aa51D` | `sna.road_remove_aa51d` | 移除边上的街道资产 |
| `SNA_OT_Assign_Road_Deef9` | `sna.assign_road_deef9` | 标记边为道路 |
| `SNA_OT_Remove_Road_A2302` | `sna.remove_road_a2302` | 取消边的道路标记 |
| `SNA_OT_Road_Lanes_Width_93562` | `sna.road_lanes_width_93562` | 车道宽度 |
| `SNA_OT_Sidewalk_Width_99Dc0` | `sna.sidewalk_width_99dc0` | 人行道宽度 |
| `SNA_OT_Crosswalk_Offset_B1E82` | `sna.crosswalk_offset_b1e82` | 人行横道偏移 |
| `SNA_OT_Intersection_Offset_16E01` | `sna.intersection_offset_16e01` | 交叉口偏移 |
| `SNA_OT_Set_Side_Count_49527` | `sna.set_side_count_49527` | 街道类型 |
| `SNA_OT_Delete_From_Scene_7C7D8` | `sna.delete_from_scene_7c7d8` | 删除道路资产 |

### 10.4 资产浏览与追加

| 类名 | bl_idname | 功能 |
|------|-----------|------|
| `SNA_OT_Read_97C87` | `sna.read_97c87` | 读取 All assets 索引文件 |
| `SNA_OT_Refresh_C6Cb8` | `sna.refresh_c6cb8` | 扫描资产目录刷新列表 |
| `SNA_OT_Refresh_Theme_443Bd` | `sna.refresh_theme_443bd` | 刷新主题列表 |
| `SNA_OT_Append_Assets_Ffd74` | `sna.append_assets_ffd74` | 追加选中资产到场景 |
| `SNA_OT_Append_Landscape_C97Bb` | `sna.append_landscape_c97bb` | 追加景观 |
| `SNA_OT_Filter_City_Assets_Ea982` | `sna.filter_city_assets_ea982` | 过滤城市资产 |
| `SNA_OT_Filter_Road_Bc600` | `sna.filter_road_bc600` | 过滤道路资产 |
| `SNA_OT_Filter_Theme_31D4C` | `sna.filter_theme_31d4c` | 按主题过滤 |
| `SNA_OT_Filter_Presets_Fb5A4` | `sna.filter_presets_fb5a4` | 过滤预设建筑 |
| `SNA_OT_Procedural_Building_Filter_05Bed` | `sna.procedural_building_filter_05bed` | 过滤程序化建筑 |
| `SNA_OT_Park_Filter_5A7A2` | `sna.park_filter_5a7a2` | 过滤公园 |
| `SNA_OT_Landscape_Filter_0Bf89` | `sna.landscape_filter_0bf89` | 过滤景观 |
| `SNA_OT_Material_Filter_F04C3` | `sna.material_filter_f04c3` | 过滤材质 |
| `SNA_OT_Road_Materials_Filter_6A3Ec` | `sna.road_materials_filter_6a3ec` | 过滤道路材质 |
| `SNA_OT_Filter_Street_Assets_C5C0E` | `sna.filter_street_assets_c5c0e` | 过滤街道资产 |

### 10.5 显示控制

| 类名 | bl_idname | 功能 |
|------|-----------|------|
| `SNA_OT_Hide_Park_3Ea8F` | `sna.hide_park_3ea8f` | 公园视口显隐 |
| `SNA_OT_Hide_Park_R_192D6` | `sna.hide_park_r_192d6` | 公园渲染显隐 |
| `SNA_OT_Grass_V_4Cdd7` / `SNA_OT_Grass_R_E07D4` | — | 草地视口/渲染显隐 |
| `SNA_OT_Trees_V_25C59` / `SNA_OT_Trees_R_164C2` | — | 树木视口/渲染显隐 |

### 10.6 UI 面板

| 类名 | 说明 |
|------|------|
| `SNA_PT_ICITY_EDITOR_6D34D` | 主编辑器面板（Start、Edit city、City/Road 操作） |
| `SNA_PT_APPEND_PANEL_590A1` | 资产追加面板 |
| `SNA_PT_ICITY_754AD` | 链接面板（Youtube、Discord、文档） |

### 10.7 偏好设置

| 类名 | 属性 | 功能 |
|------|------|------|
| `SNA_AddonPreferences_7CCE1` | `sna_assets_path` | 自定义资产库根路径（默认为插件内 assets/Assets） |

---

## 11. 全局状态变量说明

插件在模块顶层用字典保存运行时状态（非 Blender 原生 PropertyGroup）：

```python
all_assets = {'sna_l': []}           # 原始索引文本解析结果

append = {
    'sna_all_assets': [],            # 全部资产枚举项 [id, name, path, icon]
    'sna_all_materials': [],         # 全部材质枚举项
    'sna_theme_filtered': [],        # 主题过滤后的资产
    'sna_city_assets_filtered': [],  # 城市资产过滤结果
    'sna_road_assets_filtered': [],  # 道路资产过滤结果
    'sna_road_materials_filtered': [], # 道路材质过滤结果
    'sna_landscape_filtered': [],    # 景观过滤结果
    ...
}

hide_assets = {
    'sna_show_all_v_park': False,    # 公园视口显示
    'sna_show_grass_v_park': False,  # 草地视口显示
    'sna_show_trees_v_park': False,  # 树木视口显示
    ...
}

materials_variables = {
    'sna_all_materials_enum': [],
    'sna_all_materials': [],
    'sna_road_materials_filtered_': [],
}

variables = {
    'sna_edit_city': False,          # 是否处于 Edit city 模式
    'sna_attributes': [],            # 当前活动对象的 Attribute 名列表
    'sna_procedural_building': [],   # 程序化建筑名称列表
    'sna_procedural_building_browser': [], # 带预览图枚举
    'sna_building_presets': [],
    'sna_building_presets_browser': [],
    'sna_park_list': [],
    'sna_park_browser': [],
    'sna_landscape_browser': [],
    'sna_street_asset': [],
    'sna_street_asset_browser': [],
    'sna_road_materials': [],
    'sna_road_materials_browser': [],
    'sna_theme': [],
    ...
}
```

**注意**：这些变量在插件重载或 Blender 重启后会丢失，需重新 Start 并 Refresh 资产。

---

## 12. 资产库与索引机制

### 12.1 索引文件格式

`assets/Assets/Default/All assets` 为文本文件，每条记录格式：

```
['资产名', '显示名', 'blend文件路径', 图标索引]
```

示例：

```
['Default building Procedural', 'Default building Procedural',
 'G:\\My Drive\\Building\\Assets\\Default\\Procedural\\Default building Procedural.blend', 0]
['Light1_Light_ICity_Default', 'Light1_Light_ICity_Default',
 'G:\\My Drive\\Building\\Assets\\Default\\Road\\Road assets.blend', 0]
```

读取时路径中的 `G:\\My Drive\\Building\\Assets` 会被替换为插件本地 `assets/Assets` 路径。

### 12.2 资产扫描流程

```
SNA_OT_Read_97C87 / SNA_OT_Refresh_C6Cb8
  │
  ├─ sna_assets_path_7BE86() 获取资产根路径（偏好设置或默认）
  ├─ 遍历主题子目录（Default 等）
  ├─ 读取 All assets / All materials 文本
  ├─ 解析为 append['sna_all_assets'] 列表
  ├─ load_preview_icon() 加载缩略图（优先资产目录下同名 .png）
  └─ 供 EnumProperty 的 items 回调动态生成 UI 选项
```

### 12.3 资产追加路径规则

| 资产类型 | append 路径后缀 | 示例 |
|----------|----------------|------|
| 程序化建筑/公园/预设 | `\Collection` | `...\Default building Procedural.blend\Collection` |
| 街道物件 | `\Object` | `...\Road assets.blend\Object` |
| 道路材质 | `\Material` | `...\Road materials.blend\Material` |
| 景观 | `\Collection` | `...\Default_Landscape 01_ICity.blend\Collection` |

### 12.4 资产分类集合

追加后的资产会被 `sna_move_to_collection()` 移动到对应集合：

| 集合名 | 内容 |
|--------|------|
| `ICity Assets` | 隐藏的总资产库 |
| `ICity_Procedural` | 程序化建筑实例 |
| `ICity_Presets` | 预设建筑 |
| `ICity_Park` | 公园 |
| `ICity_Light` | 路灯 |
| `ICity_Bench` | 长椅 |
| `ICity_Tree` | 树木 |
| `ICity_Services` | 服务设施 |
| `ICity_Imperfection` | 瑕疵/细节 |
| `ICity_Materials` | 道路材质 |

---

## 13. test.py 说明

`test.py` 是课程提供的**独立实验脚本**，演示如何用 **BMesh** 直接编辑 `ICity Base` 网格几何，**不经过 Attribute 机制**。

### 13.1 脚本流程

```python
import bpy
import bmesh

obj = bpy.data.objects["ICity Base"]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')

bm = bmesh.from_edit_mesh(obj.data)
vert = [(x, y, z), ...]  # 预定义顶点坐标列表
vertices = [bm.verts.new(v) for v in vert]
for i in range(10):
    bm.edges.new((vertices[i], vertices[i + 1]))

bmesh.update_edit_mesh(obj.data)
bpy.ops.object.mode_set(mode='OBJECT')
```

### 13.2 与插件本体的区别

| 对比项 | test.py | 插件本体 |
|--------|---------|----------|
| API 层级 | BMesh 底层 | Attribute + Operator 高层 |
| 修改对象 | 顶点/边几何 | 面/边 Attribute 值 |
| 触发机制 | 直接改 mesh.data | Geometry Nodes 读 Attribute 生成 |
| 使用场景 | 理解城市边界网格结构 | 正常城市编辑工作流 |

### 13.3 运行前提

- 必须先执行插件 **Start**，确保 `ICity Base` 对象存在
- 在 Blender Scripting 面板或 Text Editor 中运行

---

## 14. 最小可运行 Python 示例

以下示例可在 Blender Scripting 面板运行（需先 Start）。

### 14.1 给选中面分配程序化建筑

```python
import bpy

obj = bpy.data.objects['ICity Base']
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')

# 写 space type = 0 (Procedural)
obj.data.attributes.active = obj.data.attributes['space type']
bpy.ops.mesh.attribute_set(value_int=0)

# 写 Procedural index = 0
obj.data.attributes.active = obj.data.attributes['Procedural index']
bpy.ops.mesh.attribute_set(value_int=0)

bpy.ops.object.mode_set(mode='OBJECT')
print("已分配程序化建筑类型")
```

### 14.2 修改道路材质

```python
import bpy

mat_name = 'Road 4 clean'  # 替换为实际材质名
mat = bpy.data.materials.get(mat_name)
if mat:
    ng = bpy.data.node_groups['Road 2']
    ng.nodes['Road'].inputs[2].default_value = mat
    bpy.data.objects['ICity Road'].update_tag(refresh={'DATA'})
    print(f"已应用材质: {mat_name}")
else:
    print(f"材质不存在: {mat_name}")
```

### 14.3 切换 Proxy 模式

```python
import bpy

proxy_on = True
bpy.context.scene.sna_proxy_mode = proxy_on
# update 回调会自动修改节点组输入
```

### 14.4 检测 Edit city 模式

```python
import bpy

# 需先 import icity 模块或直接访问 variables
# 等价逻辑：
edit_city = (
    bpy.context.mode == 'EDIT_MESH'
    and bpy.context.view_layer.objects.active
    and bpy.context.view_layer.objects.active.name == 'ICity Base'
)
print(f"Edit city 模式: {edit_city}")
```

---

## 15. 课程分析要点

### 15.1 架构分析

1. **三层分离**：Python 控制层 + Geometry Nodes 引擎层 + `.blend` 数据层，是典型的 Blender 插件架构模式。
2. **数据驱动设计**：城市布局参数存储在 `ICity Base` 的 Attribute 中，而非创建大量独立对象，便于批量生成与参数化修改。
3. **声明式 UI**：Panel 的 `draw()` 方法纯声明 UI 布局，Operator 的 `execute()` 执行逻辑，符合 Blender 插件规范。

### 15.2 软件工程评价

| 维度 | 评价 |
|------|------|
| **功能完整性** | 高：覆盖城市/道路/资产/材质/显隐全流程 |
| **模块化** | 低：3500 行单文件，大量重复 helper |
| **可维护性** | 低：可视化工具生成，类名不可读，难以定位逻辑 |
| **可测试性** | 低：强依赖 Blender 运行时环境，全局变量多 |
| **可扩展性** | 中：资产库可扩展，但核心逻辑耦合在单文件 |
| **性能** | 中：Geometry Nodes 计算量大，提供 Proxy 模式缓解 |

### 15.3 可视化开发 vs 手写代码

| 对比 | 可视化脚本（Serpens 等） | 手写模块化 |
|------|--------------------------|------------|
| 开发速度 | 快 | 慢 |
| 代码可读性 | 差（哈希命名） | 好 |
| 版本控制 | 难 diff | 易 diff |
| 团队协作 | 难 | 易 |
| 适合场景 | 原型、个人插件 | 产品级、团队项目 |

### 15.4 实验建议

1. **Start → Edit city → Assign** 走通完整 UI 流程，观察 Outliner 中集合变化。
2. 在 Scripting 面板运行 Attribute 写入示例，对比 UI 操作效果。
3. 用 `test.py` 理解 BMesh 与 Attribute 两种网格操作方式的区别。
4. 打开 `ICity start.blend` 查看 Geometry Nodes 如何读取 Attribute（需 Blender 内操作）。
5. 分析 `All assets` 索引格式，尝试添加自定义资产条目。

### 15.5 依赖关系与常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `Object 'ICity Base' not found` | 未执行 Start | 先点击 Start |
| Operator 按钮灰色 | 不在 Edit city 模式 | 点击 Edit city |
| 资产列表为空 | 未 Refresh | 偏好设置中 Read files |
| Attribute 写入无效 | 未选中面/边 | 在 EDIT 模式选中元素 |

---

## 16. 附录：关键代码片段索引

| 功能 | 文件位置（__init__.py 行号约） |
|------|-------------------------------|
| bl_info 元信息 | 第 14–25 行 |
| 全局变量定义 | 第 34–41 行 |
| get_blend_contents() | 第 44–48 行 |
| sna_set_active_attribute_* | 第 285–530 行 |
| sna_update_sna_proxy_mode | 第 246–250 行 |
| SNA_OT_Start（初始化） | 第 1466–1499 行 |
| SNA_OT_City_Apply | 第 1502–1538 行 |
| depsgraph handler（edit city） | 第 1541–1544 行 |
| SNA_OT_Road_Apply | 第 1548–1585 行 |
| SNA_OT_Edit_City | 第 2040–2063 行 |
| SNA_OT_Append_Assets | 第 1908–1990 行 |
| SNA_PT_ICITY_EDITOR（主面板） | 第 2449–3307 行 |
| register() | 第 3333–3432 行 |
| unregister() | 第 3435–3535 行 |

---

## 17. 关键节点组说明

以下节点组存在于 `ICity start.blend` 中，Python 通过名称直接访问：

| 节点组名 | 用途 |
|----------|------|
| `Road 2` | 道路生成主逻辑，含 Road/Curb/Sidewalk/Light/Bench 等输入 |
| `Spaces` | 城市空间（面区域）生成 |
| `Light mode` | 控制编辑模式下灯光预览 |
| `ICity Proxy` | 代理模式（低模） |
| `Hide viewport input` | 视口显隐控制 |

---

*文档生成日期：2026-05-23*  
*基于 ICity v1.0.3 源码分析*
