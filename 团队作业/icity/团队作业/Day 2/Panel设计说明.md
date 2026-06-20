# Day 2：Panel 方案说明 — 子区域 vs 新 Panel

## 结论（已采用）

**注册独立新 Panel：`Smart City Generator`（`SCG_PT_smart_city_generator`）**

**不**在 `SNA_PT_ICITY_EDITOR_6D34D`（ICity editor）内部增加子区域。

## 对比

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A. 新 Panel（采用）** | 新建 `ui/panel_smart_city.py`，`bl_category='ICity'` | 不改 3000+ 行生成代码；与 B 合并冲突小；作业名清晰 | 侧边栏多一块面板 |
| **B. 子区域** | 改 `SNA_PT_ICITY_EDITOR_6D34D.draw()` | 全在一个面板里 | 易破坏 Start/Edit；Serpens 再生代码会覆盖；难维护 |
| **C. 新分类 Tab** | `bl_category='Smart City'` | 与 ICity 完全分离 | 用户要切换 Tab；演示时要切两次 |

## 在 Blender 中的位置

- 侧边栏 **N** → 选项卡 **ICity**
- 面板顺序（当前配置）：
  1. **ICity editor**（`bl_order = 0`）— 未 Start 时仅图标 + Start；Start 后 Edit / City·Road / 资产图
  2. **ICity**（链接，`bl_order = 4`）
  3. **Smart City Generator**（`bl_order = 5`，默认折叠）— 团队功能，**不含** City·Road

## UI 显示节奏（与 ICity editor 对齐）

| 状态 | ICity editor | Smart City Generator |
|------|----------------|----------------------|
| 未 Start | 图标 + Start | 仅 Start（`scg.start_icity` → `sna.start_5209e`） |
| 已 Start | Edit、City·Road、资产预览等 | Edit City、区域 **1～8**（生成/纹理/路灯/模板/布局/动态/NL/渲染占位） |

未 Start 时 **不显示** Edit City 按钮，避免 `ICity Base` KeyError。

## 已知现象（ICity 原有）

部分 Road 资产预览图（如路灯）在 Start 后可能空白，切换 Street 类型再切回后会刷新。属 ICity 枚举/过滤刷新问题，团队面板不重复实现资产浏览器。

## 如何保留 ICity Start / Edit

新 Panel **不复制** Start/Edit 逻辑，只提供：

```python
layout.operator("sna.start_5209e", ...)
layout.operator("sna.edit_city_d7cab", ...)
```

团队新功能放在 **SCG_** 前缀的 Operator 中，内部再 `bpy.ops.sna.*` 调用 ICity。

## 代码入口

| 文件 | 作用 |
|------|------|
| `scg_register.py` | 统一 register / unregister |
| `ui/panel_smart_city.py` | Panel + 占位 Operator |
| `operators/generate_base.py` | `scg.generate_base_city`（Day 2-3 完善） |
| `__init__.py` 末尾 | `scg_register.register()` |

## 验证步骤（Day 2）

1. Blender → 脚本 → 重新加载脚本 / 禁用再启用 ICity 插件  
2. 3D 视图 → N → **ICity**  
3. 应看到 **Smart City Generator** 面板（可在列表最上方）  
4. 原 **ICity editor** 中 Start、Edit City 仍可用  
5. 点击 Smart City 中 **Start** / **Edit City** 行为与原来一致  
