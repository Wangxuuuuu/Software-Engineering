# Day 5-6 工作总结：道路纹理（2D 资产）

> 阶段二 §5.1.1 完成记录；验收 **A3** 功能已通过（2026 本地验证）。

---

## 1. 完成内容概览

| 项 | 结果 |
|----|------|
| 团队新增 2D 资产 | `assets/team/textures/road_type2.jpg`（BaseColor） |
| 场景纹理替换 | Smart City 类型1/2 +「应用道路纹理」/「生成基础城市」 |
| 换图不改代码 | 固定 `road_type1.jpg` / `road_type2.jpg` 文件名 |
| 代码 | `assets_manager.py`、`city_generator.set_road_texture`、`operators/road_texture.py`、面板区域 2 |

---

## 2. 验证记录

**环境**：Blender 4.1+，视口 **材质预览**，已 Start。

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | 类型1 → `scg.apply_road_texture` | ICity Road 4 clean **PBR 回退**（无 `road_type1.jpg`） |
| 2 | 类型2 → `scg.apply_road_texture` | **团队 `road_type2.jpg`** 生效，路面明显不同 |

**Info 日志示例**：

```text
已应用道路纹理：团队路面 类型2（road_type2.jpg · BaseColor）
（请使用视口「材质预览」或「渲染」查看）
```

**待办**：类型1 vs 类型2 对比截图 → `团队作业/screenshots/`（演示/文档用，非阻塞）。

---

## 3. 机制说明（assets_manager ↔ city_generator）

### 3.1 总流程

```text
面板 scg_road_type（类型1/2）
    │
    ▼
scg.apply_road_texture  或  generate_base_city
    │
    ▼
city_generator.set_road_texture(type_id)
    │
    ├─ assets_manager.road_texture_paths(type_id)   ← 解析用哪张图
    ├─ _build_road_material(type_id)                ← 拼 Blender 材质
    ├─ Road 2.nodes["Road"].inputs[2] = 材质      ← 写入 ICity 道路节点
    └─ _flush_viewport_refresh()                    ← 刷新视口
```

与 ICity 原生 Road→Texture 相同落点：**`Road 2` 节点组里 `Road` 节点的材质输入**；Smart City 用参数 `type_id` 批量替换，无需手选边。

---

### 3.2 `core/assets_manager.py` — 路径与策略

**职责**：决定「类型1/2 各用哪些贴图」，不操作 Blender 场景。

| 符号 / 函数 | 作用 |
|-------------|------|
| `TEAM_ROAD_BASECOLOR` | 固定路径：`road_type1.jpg`、`road_type2.jpg` |
| `_resolve_road_set(type_id)` | **有团队 jpg → 仅 BaseColor**；**无文件 → `ICITY_PBR_FALLBACK`** |
| `road_texture_paths()` | 对外返回 `{ color, normal, roughness, …, label }` |
| `road_texture_available()` | 团队 color 文件或 ICity 回退资源是否可用 |
| `road_texture_label()` | 面板 / Info 显示用文案 |

**解析规则（当前验证状态）**：

| 类型 | `assets/team/textures/` | 实际使用 |
|------|-------------------------|----------|
| 1 | 无 `road_type1.jpg` | ICity `Road 4 clean` 全套 PBR（回退） |
| 2 | **有** `road_type2.jpg` | **仅** 该文件作 BaseColor（团队新增资产） |

后续：放入 `road_type1.jpg` 即自动覆盖类型1，**无需改代码**。

---

### 3.3 `core/city_generator.py` — 材质与写入

**职责**：读 `assets_manager` 的路径 → 建材质 → 挂到 ICity 道路管线。

| 函数 | 作用 |
|------|------|
| `_build_road_material(type_id)` | 用 `road_texture_paths()` 加载图片，节点树：`Image Texture` → `Principled BSDF` → `Material Output`；有 Normal/Roughness 时一并接入（团队单图时只有 Base Color） |
| `set_road_texture(type_id)` | 入口：检查 `Road 2` → 建/更新 `SCG_Road_Type{type_id}` 材质 → 写入 `Road` 节点 → 刷新 |
| `_apply_road_texture(index)` | 「生成基础城市」内调用，`index+1` 转 `type_id` |

**Material 命名**：`SCG_Road_Type1` / `SCG_Road_Type2`（可在 Blender 材质库中看到）。

---

### 3.4 与作业要求的对应

| 作业要求 | 实现 |
|----------|------|
| 新增至少一种 2D 资产 | `road_type2.jpg`（BaseColor） |
| 场景中纹理替换 | `set_road_texture` → `Road 2` |
| 不破坏 ICity | 未改 `SNA_*`；复用同一 `Road 2` 接口 |

---

## 4. 相关文件

| 路径 | 说明 |
|------|------|
| `core/assets_manager.py` | 贴图路径、团队/回退策略 |
| `core/city_generator.py` | `set_road_texture`、材质构建 |
| `operators/road_texture.py` | `scg.apply_road_texture` |
| `ui/panel_smart_city.py` | 区域 2「道路纹理」 |
| `assets/team/textures/road_type2.jpg` | 团队新增主贴图 |

---

## 5. 相关文档

- [道路纹理Day5-6.md](./道路纹理Day5-6.md) — 贴图参考、使用步骤
- [Day 2-3/资产机制说明.md](../Day%202-3/资产机制说明.md) — 树木/座椅与 ICity 资产库
- [待办工作流程及时间线.md](../待办工作流程及时间线.md) §5.1.1、A3

## 6. 下一步

§5.1.2 **Day 6-7 路灯**（3D 资产，验收 A4）
