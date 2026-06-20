# Day 7-8：templates.json 与模板应用（阶段二 §5.1.3）

> 验收 **A5**：**已通过**（2026 本地验证；模板 0/1 树/路/椅/密度/昼夜明显不同，路灯均为 ICity 默认）。

## 验证记录（已通过）

| 项 | 结果 |
|----|------|
| 面板「4. 模版选择」+ 编号 0/1 +「应用模板」 | ✅ |
| 模板 0：树1、路2、椅1、密度 medium、day | ✅ |
| 模板 1：树2、路1、椅2、密度 high、night | ✅ |
| 模板 0 ↔ 1 视觉明显不同 | ✅ |
| 路灯：两模板均为 ICity 默认 + Sun；night 下可发光 | ✅ |

**Info 日志示例**：

```text
已应用模板 0：树1，路2，椅1，密度medium，day
已应用模板 1：树2，路1，椅2，密度high，night
```

**待 Day 9**：模板 0 vs 1 对比截图 → `团队作业/screenshots/`（演示用，非阻塞）。

---

## 验证清单（参考）

| 项 | 操作 | 预期 |
|----|------|------|
| 模板 0 | Smart City **区域 4** → 编号 `0` → **应用模板** | 树1、路2（团队贴图）、椅1、密度中、白天、无团队路灯 |
| 模板 1 | 编号 `1` → **应用模板** | 树2、路1、椅2、密度高、夜间背景；**路灯仍为 ICity 默认**（与模板 0 一致） |
| 对比 | 0 应用后再 1 | 树/路/椅/建筑密度/昼夜 **肉眼明显不同** |
| Info | 查看 Blender Info | `已应用模板 N：树…，路…，椅…，密度…，day/night…` |

**视口建议**：材质预览或渲染；模板 1 可看世界背景变暗 + 路灯实例。

---

## 使用步骤

1. **Start ICity**（或已有 ICity 场景）
2. Smart City 面板 → **区域 4. 模版选择**
3. 输入 **模板编号**（0 或 1）
4. 阅读下方 **说明** 行确认配置摘要
5. 点击 **应用模板**（一键：写参数 → 环境 → 生成城市）

无需先手动点「生成基础城市」；应用模板会调用 `generate_base_city_from_scene`。

---

## 模板配置（config/templates.json）

| 键 | 树 | 路 | 椅 | 密度 | 天气 |
|----|----|----|----|------|------|
| 0 | 1 | 2 | 1 | medium | day |
| 1 | 2 | 1 | 2 | high | night |

路灯不在 JSON 中配置：ICity 默认路灯始终开启（day/night 均有 Sun）；团队 `Street_Lamp` 仅通过 **区域 3** 手动替换。

---

## 机制（简短）

```text
scg.apply_template
  → template_manager.apply_template
      1. apply_scene_properties_from_template（scg_tree/road/bench/density/night）
      2. set_environment(weather) → sna_light_mode + 世界 Background + light_city
      3. generate_base_city_from_scene（含道路纹理 + ICity 默认路灯）
      （不调用 apply_street_lights；团队路灯仅在区域 3 手动添加）
```

**模块**：

| 文件 | 作用 |
|------|------|
| `config/templates.json` | 模板 0/1 数据 |
| `core/template_manager.py` | 读 JSON、`apply_template`、环境预置 |
| `operators/apply_template.py` | `scg.apply_template` |
| `scg_properties.py` | `scg_template_id` |
| `ui/panel_smart_city.py` | 区域 4 |

**主文档 §5.1.3 面板「区域 2」**：与现有 UI 编号冲突，实际放在 **区域 4「模版选择」**（区域 2 为道路纹理）。

---

## 与 Day 5-6 / Day 6-7 的关系

- **道路**：模板写入 `scg_road_type` 后由 `generate_base_city` 内 `_apply_road_texture` 生效（同 Day 5-6）。
- **路灯**：模板应用 **不** 替换为团队 `Street_Lamp.blend`，始终用 `generate_base_city` 的 ICity 默认路灯；团队路灯仍通过 **区域 3「添加路灯」** 手动使用。

---

## 待 Day 9 收尾

- [ ] 截图：模板 0 vs 1 → `团队作业/screenshots/`
- [ ] 同步 templates.json 给 LLM / 前端同学
- [x] A5 勾选 + Day 7-8 实现验证
- [ ] 阶段二复盘（Day 9）
