# Day 6-7：路灯 3D 资产（阶段二 §5.1.2）

> 验收 **A4**：**已通过**（团队路灯替换外圈道路原路灯，尺寸/方向/材质正常）。  
> 夜间 Emission / 每盏灯 Sun 点光 → **后续需要时再做**（模板 1 night 等）。

## 验证记录（已通过）

| 项 | 结果 |
|----|------|
| 添加路灯 → 外圈竖灯、替换 ICity 原路灯 | ✅ |
| 尺寸与方向（normalize + 非中心辐条边） | ✅ |
| 材质预览下颜色正常（贴图重连） | ✅ |
| 勾选「路灯夜间 Emission」渲染发光明显 | ⏸ 暂缓（当前仅弱 Emission，够用可后补） |
| 实体模式每盏灯旁 Sun 图标（Blender Light） | ⏸ 暂缓（团队模型无子级 Light，属预期） |

## 你的资产文件夹是什么意思？

| 路径 | 含义 |
|------|------|
| `lamp/Street_Lamp.blend` | **3D 模型包**：Blender 工程，内含路灯 **Object**（名称 `Street_Lamp`）、网格、材质 |
| `lamp/Textures/`（及同级 `lamp_*.png`） | **PBR 贴图**：给路灯材质用的颜色/法线/发光等；由 `.blend` 内材质引用，**无需插件单独加载** |

作业「新增 3D 资产」= 把 `Street_Lamp.blend` 放进 `assets/team/models/` 并通过代码 **append 进场景**。

## 使用步骤

1. Start → **生成基础城市**（生成道路，默认 Light 边属性为关）
2. Smart City **区域 3** → 可选勾选 **路灯夜间发光**
3. 点击 **添加路灯**
4. 材质预览 / 渲染下查看道路两侧

## 机制（简短）

```text
scg.apply_street_lights
  → street_lights.append Team Street_Lamp.blend
  → 移入 ICity_Light 集合
  → ICity Base 边 Attribute Light = True
  → Road 2.nodes["Light"].inputs[4] = 路灯 Object
  → 几何节点沿路实例化
```

| 模块 | 职责 |
|------|------|
| `assets_manager.py` | `STREET_LIGHT_BLEND`、`STREET_LAMP_OBJECT_NAME` |
| `core/street_lights.py` | `apply_street_lights()` / `add_street_lights()` |
| `operators/street_lights.py` | `scg.apply_street_lights` |

换模型：替换 `Street_Lamp.blend`（保持 Object 名 `Street_Lamp` 或改 `assets_manager.STREET_LAMP_OBJECT_NAME`）。

## 常见问题

### 路灯巨大、呈放射状铺满城市？

**三个叠加原因（非 Start 自带路灯冲突）：**

1. **边 Attribute 写错范围**：旧代码对 `ICity Base` **全部边** 设 `Light=True`。该网格含从**中心枢纽**连向外的辐条边，几何节点会沿每条辐条实例化 → 放射状平面。
   - **修复**：仅对「道路边且不过中心枢纽顶点」的边开 `Light`（见 `street_lights._enable_light_on_street_edges`）。
2. **模型尺度**：`Street_Lamp.blend` 单位常与 ICity 城市场景不一致（导入模型偏大）。
   - **修复**：追加后按 `ICity_Light` 内官方路灯尺寸缩放。
3. **模型轴向**：模板 Object 若「躺平」，实例化时会沿道路切线躺倒。
   - **修复**：追加后检测并绕 X 轴扶起，再 `transform_apply`。

**与 ICity 默认路灯**：Start 后路灯光靠 `Road 2` 的 Light 节点引用；点击「添加路灯」会**替换**该引用为 `SCG_Team_Street_Lamp`，不是两套叠加冲突。

**建议重试前**：删除场景中已有 `SCG_Team_Street_Lamp`（若缩放已错误），或重新 Start 后再「生成基础城市」→「添加路灯」。

### 路灯是粉紫色、像「没贴图」？

Blender 里 **洋红/粉紫** 几乎总是 **材质引用的贴图文件找不到**（missing texture），不是 ICity 冲突。

`Street_Lamp.blend` append 进场景后，材质节点仍可能指向 **制作机器上的旧路径**；本地应对照：

- `assets/team/models/lamp/Textures/lamp_basecolor.png` 等

**修复**：插件在「添加路灯」时会按 **文件名** 在上述目录自动重连贴图。请重载插件后再点一次「添加路灯」。

若仍发粉：在 Blender 中打开 `Street_Lamp.blend` → File → **External Data → Pack Resources** 再保存，或确认 `Textures/` 内文件名与材质节点一致。

### 夜间 Emission 很弱 / 没有 Sun 图标？

- **Emission 弱**：当前仅对 Principled BSDF 做简单 Emission；团队材质若主要走 `lamp_emissive.png` 节点链，可能几乎不亮。**A4 不依赖此项**，模板 1 夜间可再加强。
- **无 Sun 图标**：ICity 原灯常带 **Light 子对象**；团队 `Street_Lamp` 纯 Mesh，几何节点只复制模型。**正常**。

## 后续可选（需要时再做）

- 加强夜间：读 `lamp_emissive.png`、提高 Strength，或 append 后挂 Point Light 子对象  
- 与模板 `weather` / ICity `sna.light_mode` 联动昼夜环境（路灯资产不由 templates.json 控制）

## 相关

- [Day5-6工作总结.md](./Day5-6工作总结.md)
- [待办工作流程及时间线.md](../待办工作流程及时间线.md) §5.1.2
