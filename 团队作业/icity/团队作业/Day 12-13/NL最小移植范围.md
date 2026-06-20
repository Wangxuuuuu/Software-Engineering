# NL 最小移植范围（单插件 · 区域 7 嵌入）

> **策略**：采用「单插件 + Smart City 区域 7 嵌入」；**不**整包迁入 `nlp_city_editor`，只移植满足实验要求与 A6 验收的**最小子集**。联调通过后再按需扩展天气粒子、镜头、快捷面板等。

**相关文档**：

- **NL/LLM 机制简介**：[`docs/nl_llm_overview.md`](../../docs/nl_llm_overview.md)
- 融合架构分析（方案对比）：见前序讨论 / 后续可补 `NL与LLM融合分析.md`
- 模板静态表：[`Day 9/templates与组内协作说明.md`](../Day%209/templates与组内协作说明.md)
- 布局（已完成）：[`布局控制进度对照.md`](布局控制进度对照.md)

---

## 1. 实验要求 → 最小能力

| 实验要求 | 最小能力 | 主要实现位置 |
|----------|----------|--------------|
| **1. 场景生成模板化** | 模板编号 / 自然语言 → 树·路·椅·密度·昼夜 → 生成城市 | SCG 已有 `templates.json`、`apply_template`；NL 负责**解析** |
| **1 补充** | 「树木、道路和座椅均设为类型 1」 | SCG 写 `scg_*` + 可选重新生成 |
| **2. 自然语言交互编辑** | 文字 → 解析 → 调 SCG/ICity 后台 | 区域 7 输入框 + `command_executor` |
| **2 示例** | 「将天色变暗」 | SCG `template_manager.set_environment(night)` |
| **2 示例** | 「切换为雨天模式」 | **阶段 1 可简化**（见 §3.3）；完整雨效属扩展项 |

**A6 验收**（主文档 §7.1.2）：≥ **5 条**中文指令稳定、无 Python 报错；**离线规则兜底**必须可用（LLM 不可用时仍能演示）。

---

## 2. 从 NLP 插件「要移植」什么（最小集）

### 2.1 建议移植（仅核心解析层）

| NLP 源文件 | 移植范围 | 迁入 ICity 目标（建议） | 说明 |
|----------|----------|-------------------------|------|
| `core/llm_backend.py` | **整文件精简** | `core/nl_llm_backend.py` | 保留 `call_llm()`、urllib、OpenAI 兼容协议；**重写** `SYSTEM_PROMPT`，只列 SCG `action`（见 §4） |
| `core/intent_engine.py` | **部分** | `core/nl_intent_engine.py` | 保留 `parse(text, use_llm)` 双模式入口；**只保留** §4 对应离线规则，删除 sky/camera/post/object 等大批规则 |
| `preferences.py` | **部分** | `scg_nl_preferences.py` 或并入 ICity `AddonPreferences` | 提供商、API Key、model、temperature、debug；**不要**提交真实密钥 |

**不移植** `scene_driver.py`：统一用 SCG 已有骨架 `core/command_executor.py` 分发 `action/params`。

### 2.2 明确不移植（第一阶段）

| NLP 模块 | 原因 |
|----------|------|
| `ui/panel_main.py` 等全部 UI | 逻辑并入 `ui/panel_smart_city.py` **区域 7** |
| `ui/panel_quick.py` / `panel_history.py` / `panel_effects.py` | 非实验最低要求；后续可选 |
| `effects/scene_objects.py` | 创建 primitive 树/楼，与 **ICity 程序化城市冲突** |
| `effects/sky_atmosphere.py` | 昼夜由 SCG `set_environment` + ICity 灯光负责 |
| `effects/lighting_rig.py` | 同上；团队路灯走 `scg.add_street_lights` |
| `effects/camera_rig.py` | 非实验要求 |
| `effects/material_fx.py` | 非实验要求 |
| `effects/weather_particles.py` | **第一阶段不移植**；「雨天」见 §3.3 简化策略 |

### 2.3 在 SCG 侧「自写」而非从 NLP 搬

| 能力 | 实现方式 |
|------|----------|
| 命令执行 | 完善 `core/command_executor.py` + 新建 `core/nl_handlers.py` |
| 模板 / 树路椅 / 生成 | 调用现有 `template_manager`、`city_generator`、`bpy.ops.scg.*` |
| 区域 7 面板 | `ui/panel_smart_city.py` + `operators/nl_execute.py` |
| 协议文档 | 新建 `团队作业/插件命令协议.md` |

---

## 3. 第一阶段支持的 action（= 最小功能清单）

与主文档 §7.1.2 及实验要求对齐，**第一阶段只注册以下 action**：

| # | 演示输入（示例） | action | params（示例） | 后端 |
|---|------------------|--------|----------------|------|
| 1 | 应用模板 0 / 使用模板一 | `apply_template` | `{"template_id": "0"}` | `template_manager.apply_template` |
| 2 | 将树木、道路和座椅均设为类型 1 | `apply_asset_config` | `{"tree_type":1,"road_texture":1,"bench_type":1}` | 写 `scg_*`，可选 `generate_base_city` |
| 3 | 将道路改为类型 2 | `set_road_texture` | `{"type": 2}` | 写 `scg_road_type` + `scg.apply_road_texture` |
| 4 | 将天色变暗 / 切换夜间 | `set_environment` | `{"mode": "night"}` | `template_manager.set_environment` |
| 5 | 切换为白天 | `set_environment` | `{"mode": "day"}` | 同上 |
| 6 | 添加车辆 | `add_dynamic_element` | `{"type": "car"}` | `dynamic_elements.add_cars_and_pedestrians` |
| 7 | 添加路灯 | `add_street_lights` | `{}` | `bpy.ops.scg.add_street_lights`（或现有 op） |

**A6 正式验收集（2026-05-23 确认，离线 + LLM 均需覆盖）**：

| # | 演示输入 | action |
|---|----------|--------|
| 1 | 将天色变暗 | `set_environment` → `night` |
| 2 | 将道路改为类型 1 | `set_road_texture` → `type: 1` |
| 3 | 应用模板 0 | `apply_template` → `template_id: "0"` |
| 4 | 将树木、道路和座椅均设为类型 1 | `apply_asset_config` |
| 5 | 添加 2 辆车辆 | `add_dynamic_element` → `type: "car"`, `count: 2` |

（主文档中的「添加路灯」「添加船只」「雨天」列为 **P3 扩展**；雨天阶段 1 走方案 A，见 §3.3。）

### 3.1 实验要求 1 覆盖说明

- 面板 **区域 4「模版选择」+ 应用模板**：已有，NL 只是多一条入口（`apply_template`）。  
- 自然语言「模板 0」与「树路椅均类型 1」分别对应 action **#1** 与 **#2**，**不需要** NLP 的 `apply_template {fn}` 原实现。

### 3.2 实验要求 2 覆盖说明

- 「天色变暗」→ **#4**，走 ICity 环境，**不**使用 NLP 的 `set_time` / Nishita 天空。  
- 可自行设计额外 NL 能力：第一阶段优先 **#6 车辆**、**#7 路灯**（与主文档演示脚本一致）。

### 3.3 「雨天模式」策略（已确认）

| 阶段 | 方案 | 状态 |
|------|------|------|
| **阶段 1（A6 / 实验演示）** | **方案 A**：识别「雨天」话术 → `set_environment` + `mode: "rainy"` → handler 调暗环境 + Info 提示「雨粒子待扩展」 | ✅ **已采用** |
| **阶段 2（扩展）** | **方案 B**：最小迁入 `weather_particles.fn_set_weather`（rain/none） | ⬜ 待 A6 通过后再做 |

阶段 1 **不**移植 NLP `effects/weather_particles.py`。

---

## 4. LLM 输出格式（统一协议，非 NLP 原 `fn/args`）

第一阶段固定为 SCG 格式（与 `command_executor` 一致），**不**沿用 NLP 的 `intent + actions[].fn`。

```json
{
  "source": "nl_input",
  "raw_text": "将树木、道路和座椅均设为类型1",
  "commands": [
    {
      "action": "apply_asset_config",
      "params": { "tree_type": 1, "road_texture": 1, "bench_type": 1 }
    }
  ],
  "reply": "已将树木、道路和座椅设为类型 1"
}
```

- `llm_backend.SYSTEM_PROMPT` 只描述 §3 中的 action / params。  
- `intent_engine` 离线模式直接产出上述 `commands`（可省略 `source/raw_text`）。  
- 可选：`core/nl_adapter.py` 若联调时 LLM 同学仍输出 `fn/args`，在此转换为 `action/params`（第一阶段可不做）。

---

## 5. 分阶段实施顺序（确认范围后再写代码）

| 阶段 | 内容 | 依赖 NLP 移植 |
|------|------|---------------|
| **P0** | `插件命令协议.md` + `nl_handlers` + `command_executor` 注册 §3 的 action | 无 |
| **P1** | 区域 7 UI + `scg.execute_nl` + **纯离线**规则（5 条） | 仅借鉴 `intent_engine` 规则写法，可手写在 SCG |
| **P2** | 迁入 `nl_llm_backend` + LLM 开关 + Prompt 联调 | 移植 `llm_backend` 精简版 |
| **P3** | 扩展：路灯、船只、布局 NL、`apply_layout` | SCG 自写 handler |
| **P4（可选）** | 雨粒子、镜头、快捷面板、历史记录 | 按需从 NLP `effects/*` 拣选 |

---

## 6. 预计修改 / 新增文件（实施 P0–P2 时）

| 文件 | 操作 |
|------|------|
| `core/command_executor.py` | 完善注册与错误信息 |
| `core/nl_handlers.py` | **新建**：§3 各 action 实现 |
| `core/nl_intent_engine.py` | **新建**：离线规则 + 调用 LLM |
| `core/nl_llm_backend.py` | **新建**：自 NLP 精简移植 |
| `operators/nl_execute.py` | 实现 `scg.execute_nl` |
| `scg_properties.py` | `scg_nl_input_text`、`scg_use_llm`、`scg_nl_status` |
| `ui/panel_smart_city.py` | 区域 7 嵌入输入框与反馈 |
| `operators/__init__.py` | 注册 NL Operator |
| `scg_register.py` | 注册 NL 偏好（若独立 preferences 文件） |
| `团队作业/插件命令协议.md` | ✅ **P0 已完成** |
| `团队作业/待办工作流程及时间线.md` | A6 勾选与联调记录 |

**不修改**：`layout_control.py`、`city_generator.restore_*`、ICity 原生 `__init__.py` 主体。

**不保留独立插件**：`nlp_city_editor` 文件夹可留作参考，交付时用户只启用 **ICity + SCG** 一个插件。

---

## 7. 与 LLM 同学的分工边界

| 负责方 | 内容 |
|--------|------|
| **插件 / 后端（你们）** | action 实现、区域 7、离线规则、协议文档 |
| **LLM 同学** | 按 `插件命令协议.md` 调整 Prompt；保证输出 **commands** JSON；提供 API 联调 |
| **共同** | §3 五条验收话术 + 每条测 3 次成功率 |

---

## 8. 确认清单（组内已确认 2026-05-23）

- [x] 第一阶段 action 列表（§3）组内确认  
- [x] 「雨天」阶段 1 采用 **方案 A**；方案 B 留阶段 2  
- [x] **A6 五条**：变暗 / 路类型 1 / 模板 0 / 树路椅均 1 / 加车  
- [x] JSON 统一为 `commands` / `action` / `params`（§4）  
- [x] 不移植 NLP primitive 物体与独立 NLP City 选项卡  

**下一步**：~~P0~~ ✅ → ~~**P1**~~ ✅ → ~~**P2**（LLM 联调）~~ ✅ → **P3** 扩展。

---

## 9. P1 验收记录（2026-05-23）

**环境**：Blender 4.1 · ICity 已 Start · 已生成基础城市 · `scg_use_llm=False`（离线）  
**方式**：Smart City **区域 7** 输入 → **执行指令** · 视口肉眼确认

| # | 输入 | Info 摘要 | 视口 |
|---|------|-----------|------|
| 1 | 将天色变为白天 | `set_environment：已切换白天环境` | ✅ |
| 2 | 将道路改为类型1 | `set_road_texture：已应用道路纹理…` | ✅ |
| 3 | 应用模板0 | `apply_template：已应用模板 0：树1，路2，椅1…` | ✅ |
| 4 | 将树木、道路和座椅均设为类型1 | `apply_asset_config：已更新资产配置…并重新生成` | ✅ |
| 5 | 添加2辆车辆 | `add_dynamic_element：车辆 2…行人 0` | ✅ |
| 6 | 将天色变暗 | `set_environment：已切换夜间环境` | ✅ |

- **A6 五条**（变暗 / 路1 / 模板0 / 树路椅均1 / 加车2辆）：✅ 全部通过，无 Python 报错  
- **补充**：白天切换 ✅；无空格话术（`类型1`、`模板0`）离线规则可识别  
- **P2 LLM**：✅ 见 §11（DeepSeek `deepseek-v4-flash`）；雨天视口验收（离线规则已自测）

---

## 10. P2 实现说明（LLM 联调）

| 文件 | 作用 |
|------|------|
| `scg_nl_preferences.py` | 区域 7 Scene 配置 + 本地 JSON 持久化 API Key |
| `core/nl_llm_backend.py` | `call_llm` + SCG `SYSTEM_PROMPT` + JSON 归一化 |
| `core/nl_intent_engine.py` | `use_llm=True` 优先 LLM，失败回退离线 |
| `ui/panel_smart_city.py` | 区域 7 LLM API 配置 + 解析来源显示 |
| `docs/nl_p2_llm_test.py` | Blender 内 LLM 解析/执行测试 |

**配置步骤**（区域 7 面板，非插件偏好页）：

1. Reload Scripts  
2. Smart City **区域 7** → 开启 **LLM** 开关  
3. 展开 **LLM API 配置**：选择提供商、填写 **API Key**、确认模型  
4. 点 **保存到本地**（写入 `Blender配置目录/icity_scg_nl.json`，重启自动加载）  
5. 输入 A6 话术 → **执行指令**  
6. 成功时 reply **不含** `LLM 回退`；失败时回退离线并在 reply 注明原因

**安全**：API Key 默认留空，仅存本机 JSON，勿提交版本库。

---

## 11. P2 验收记录（2026-05-23）

**环境**：Blender 4.1 · DeepSeek API · 模型 `deepseek-v4-flash` · `scg_use_llm=True`  
**配置**：区域 7 LLM API → Key 保存至 `icity_scg_nl.json`

| 验证项 | 结果 |
|--------|------|
| DeepSeek 用量页有 API 调用记录 | ✅ |
| 面板 `成功[LLM]：…` | ✅ |
| 面板 `解析来源：LLM（DeepSeek 等大模型）` | ✅ |
| Info `解析来源：LLM` | ✅ |
| 执行 `添加2辆车辆` → 车辆 2、行人 0 | ✅ |
| 无 `LLM 回退` 后缀 | ✅ |

**结论**：P2 LLM 联调验收通过；A6 离线 + LLM 双路径均可演示。
