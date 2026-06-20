# Smart City 自然语言 / LLM 模块说明

> **版本**：P2（2026-05-23）  
> **位置**：ICity 插件内 Smart City 面板 **区域 7**  
> **状态**：离线规则 + DeepSeek LLM 双模式已验收，当前阶段不再扩展其他 LLM 能力。

---

## 1. 设计目标

将用户的中文自然语言指令，转换为统一的 **commands JSON**，再调用 SCG 已有后台（模板、道路、环境、动态元素等），实现：

- **实验要求**：场景模板化 + 自然语言交互编辑（A6 ≥ 5 条稳定指令）
- **演示可靠**：LLM 不可用时，离线规则仍可完整演示
- **单插件交付**：不依赖独立 `nlp_city_editor` 插件

---

## 2. 整体机制

```
用户输入（区域 7）
       ↓
parse_nl_input()          ← core/nl_intent_engine.py
  ├─ LLM 开启 → call_llm() → JSON 归一化     ← core/nl_llm_backend.py
  └─ 失败 / 关闭 → offline_parse() 正则规则
       ↓
commands JSON（action + params）
       ↓
execute_commands()        ← core/command_executor.py
       ↓
nl_handlers 各 action     ← core/nl_handlers.py
       ↓
SCG 后台（模板 / 生成 / 贴图 / 环境 / 车辆…）
```

**一条用户话可对应多条 command**，按数组顺序依次执行。

### 统一 JSON 格式

与 [`团队作业/插件命令协议.md`](../团队作业/插件命令协议.md) 一致：

```json
{
  "source": "llm",
  "raw_text": "添加2辆车辆",
  "commands": [
    { "action": "add_dynamic_element", "params": { "type": "car", "count": 2 } }
  ],
  "reply": "已添加 2 辆车辆"
}
```

| 字段 | 说明 |
|------|------|
| `source` | `llm` / `offline_rule` / `unknown` |
| `commands` | 有序命令列表（必填） |
| `action` | 见 §4 |
| `params` | 各 action 参数，默认 `{}` |
| `reply` | 中文摘要，供面板与 Info 显示 |

---

## 3. 双模式解析

| 模式 | 触发条件 | 实现 |
|------|----------|------|
| **LLM** | 区域 7 开启 LLM 开关 + 已配置 API Key | DeepSeek 等 OpenAI 兼容 API |
| **离线** | LLM 关闭，或 LLM 调用失败 | `offline_parse()` 关键词 / 正则 |

**回退策略**：LLM 开启时优先请求大模型；若 Key 缺失、网络错误或返回无效 JSON，自动回退离线规则，并在 reply 中标注 `LLM 回退：…`（成功走 LLM 时面板显示 `成功[LLM]`）。

---

## 4. 已实现的 action

| action | 功能 | 示例话术 |
|--------|------|----------|
| `apply_template` | 应用 `templates.json` 模板并生成 | 应用模板 0 |
| `apply_asset_config` | 树 / 路 / 椅类型 + 可选重新生成 | 将树木、道路和座椅均设为类型 1 |
| `set_road_texture` | 仅切换道路贴图 | 将道路改为类型 1 |
| `set_environment` | 昼夜 / 雨天（雨天为环境变暗，无雨粒子） | 将天色变暗、切换白天、雨天模式 |
| `add_dynamic_element` | 车辆 / 行人 / 船只 | 添加2辆车辆（仅车，行人 0） |
| `add_street_lights` | 添加路灯（已注册，NL 话术待 P3 扩展） | — |

**A6 正式验收五条**：变暗 / 路类型 1 / 模板 0 / 树路椅均 1 / 加 2 辆车。

---

## 5. LLM 接入（P2）

### 5.1 配置方式

在 **Smart City → 区域 7** 开启 LLM 后，展开 **LLM API 配置**：

| 项 | 推荐值（DeepSeek） |
|----|-------------------|
| 提供商 | DeepSeek |
| Base URL | `https://api.deepseek.com`（自动填入） |
| 模型 | `deepseek-v4-flash` |
| API Key | 在 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 申请 |
| Temperature | `0.05`（默认） |

填写后点 **保存到本地**，写入：

```text
Blender配置目录/icity_scg_nl.json
```

重启 Blender 后自动加载 Key（无需重复粘贴）。

### 5.2 技术实现

- **协议**：OpenAI 兼容 `POST /v1/chat/completions`
- **依赖**：纯 `urllib`，无第三方包
- **Prompt**：`core/nl_llm_backend.py` 内 `SYSTEM_PROMPT`，仅描述 §4 的 action，要求输出 `commands` JSON
- **JSON 模式**：DeepSeek / OpenAI 等提供商自动附加 `response_format: json_object`

### 5.3 如何确认走了 LLM

| 位置 | 成功走 LLM 时的表现 |
|------|---------------------|
| 面板状态 | `成功[LLM]：…` |
| 面板来源行 | `解析来源：LLM（DeepSeek 等大模型）` |
| Info | `解析来源：LLM` |
| DeepSeek 用量页 | 有 API 调用记录 |
| 调试日志开启时 | 控制台 `[SCG LLM] POST https://api.deepseek.com/v1/chat/completions` |

### 5.4 API 调用与 JSON 转化流程

本节说明：**如何把用户中文** 通过 HTTP 发给大模型，再**可靠地变成** `command_executor` 能执行的 `commands` JSON。实现集中在 `core/nl_llm_backend.py`。

#### 5.4.1 调用链路（三步）

```
用户文本 user_text
    │
    ▼
call_llm(user_text)              # 发 HTTP 请求，拿回 LLM 原始 JSON
    │
    ▼
normalize_llm_response(raw, …)   # 清洗、字段映射、白名单过滤
    │
    ▼
call_llm_and_to_payload(…)       # 组装最终 payload（source=llm）
    │
    ▼
execute_commands(context, payload)
```

入口函数为 `call_llm_and_to_payload()`；`parse_nl_input(use_llm=True)` 在 P2 中调用它。

#### 5.4.2 如何构造 API 请求

1. 从区域 7 配置读取参数（`get_nl_settings()`）：`api_key`、`base_url`、`model`、`temperature`、`provider`。
2. 拼接 OpenAI 兼容地址，例如 DeepSeek：
   ```text
   https://api.deepseek.com  →  https://api.deepseek.com/v1/chat/completions
   ```
3. 组装请求体（`POST` + `Content-Type: application/json` + `Authorization: Bearer <key>`）：

```json
{
  "model": "deepseek-v4-flash",
  "temperature": 0.05,
  "max_tokens": 2048,
  "response_format": { "type": "json_object" },
  "messages": [
    { "role": "system", "content": "<SYSTEM_PROMPT>" },
    { "role": "user",   "content": "添加2辆车辆" }
  ]
}
```

| 字段 | 作用 |
|------|------|
| `messages[0]`（system） | `SYSTEM_PROMPT`：规定**只能**输出 `commands` + `reply`，并列出 6 个合法 `action` 及 `params` 含义 |
| `messages[1]`（user） | 用户原始中文 |
| `response_format` | 要求模型返回纯 JSON 对象（DeepSeek / OpenAI / 火山等支持时自动附加） |
| `temperature: 0.05` | 偏低，减少随意发挥，提高指令解析稳定性 |

**Prompt 是格式约束的核心**：模型不被允许输出 NLP 旧版的 `fn` / `intent` / `actions`，只能按 SCG 协议写 `action` / `params`。

#### 5.4.3 解析 HTTP 响应

API 返回的标准结构（OpenAI 格式）：

```json
{
  "choices": [
    { "message": { "content": "{ \"commands\": [...], \"reply\": \"...\" }" } }
  ]
}
```

代码从 `choices[0].message.content` 取出字符串后，依次做：

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `_strip_json_fence()` | 去掉模型偶尔包裹的 ` ```json … ``` ` |
| 2 | `json.loads()` | 解析为 Python dict |
| 3 | 正则兜底 | 若解析失败，用 `re.search(r"\{.*\}")` 提取首个 JSON 对象再解析 |

此时得到的是 **LLM 原始 JSON**（仍可能字段名不标准，见下一节）。

#### 5.4.4 归一化为 SCG 目标格式

`normalize_llm_response()` 把 LLM 原始 JSON 转为 executor 统一 payload：

**输入（LLM 理想输出）示例：**

```json
{
  "commands": [
    { "action": "add_dynamic_element", "params": { "type": "car", "count": 2 } }
  ],
  "reply": "已添加 2 辆车辆"
}
```

**输出（插件内部标准 payload）：**

```json
{
  "source": "llm",
  "raw_text": "添加2辆车辆",
  "commands": [
    { "action": "add_dynamic_element", "params": { "type": "car", "count": 2 } }
  ],
  "reply": "已添加 2 辆车辆"
}
```

归一化时额外补充了 `source` 与 `raw_text`，供面板显示解析来源。

**逐条 command 清洗（`_normalize_command()`）：**

| 处理 | 说明 |
|------|------|
| 字段兼容 | `params` 缺失时尝试读 `args`；仅有 `fn` 时映射为 `action`（旧 NLP 格式容错） |
| 模板 ID | `id` / `template` → 统一为 `template_id` 字符串 |
| 道路类型 | `road_type` / `road_texture` → 统一为 `type` 整数 |
| 环境模式 | `dark` / `dusk` / `rain` → 统一为 `night` / `day` / `rainy` |
| 白名单 | 仅保留 `VALID_ACTIONS` 中的 6 个 action，未知 action 整条丢弃 |
| 多命令 | `commands` 数组按顺序保留；若 LLM 误用 `actions` 字段也会尝试读取 |

若归一化后 `commands` 为空，则抛出错误，`parse_nl_input` 捕获后**回退离线规则**。

#### 5.4.5 完整示例

**用户输入：** `将天色变暗并添加2辆车辆`

**LLM 可能返回：**

```json
{
  "commands": [
    { "action": "set_environment", "params": { "mode": "night" } },
    { "action": "add_dynamic_element", "params": { "type": "car", "count": 2 } }
  ],
  "reply": "已切换夜间环境并添加 2 辆车辆"
}
```

**归一化后** 原样保留两条 command（均在白名单内），`execute_commands` 按顺序执行：

1. `set_environment` → 调暗天色  
2. `add_dynamic_element` → 仅加 2 辆车（行人临时置 0）

#### 5.4.6 与离线规则的关系

| 环节 | LLM 路径 | 离线路径 |
|------|----------|----------|
| 产出 JSON | 模型根据 Prompt 生成 | `offline_parse()` 正则匹配 |
| 目标格式 | 相同：`{ source, raw_text, commands, reply }` | 相同 |
| 执行 | 同一套 `execute_commands` + `nl_handlers` | 同一套 |

因此无论走 LLM 还是离线，**下游执行层完全共用**，区别仅在「谁生成 commands JSON」。

---

## 6. 关键文件

| 文件 | 职责 |
|------|------|
| `ui/panel_smart_city.py` | 区域 7 UI：输入框、LLM 开关、API 配置、状态显示 |
| `operators/nl_execute.py` | `scg.execute_nl` / `scg.save_nl_api_settings` |
| `core/nl_intent_engine.py` | 解析入口：LLM + 离线 |
| `core/nl_llm_backend.py` | LLM 请求、Prompt、响应归一化 |
| `scg_nl_preferences.py` | API 配置读写、本地 JSON 持久化 |
| `core/command_executor.py` | commands 分发 |
| `core/nl_handlers.py` | 各 action 具体实现 |
| `scg_properties.py` | Scene 属性（输入文本、LLM 开关、API 字段等） |

### 测试脚本（可选）

| 脚本 | 用途 |
|------|------|
| `docs/nl_p0_manual_test.py` | 直接喂 JSON，测 command 执行 |
| `docs/nl_p1_offline_test.py` | 终端测离线解析（无需 Blender） |
| `docs/nl_p1_manual_test.py` | Blender 内离线全链路 |
| `docs/nl_p2_llm_test.py` | Blender 内 LLM 解析 / 执行 |

---

## 7. 阶段划分（已完成部分）

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0 | 命令协议 + `nl_handlers` + `command_executor` | ✅ |
| P1 | 区域 7 UI + 离线规则（A6 五条） | ✅ |
| P2 | DeepSeek LLM 联调 + 解析来源显示 + API 本地保存 | ✅ |
| P3+ | 路灯 / 船只 / 布局 NL、雨粒子等 | 未做（按需） |

---

## 8. 相关文档

- 命令协议详表：[`团队作业/插件命令协议.md`](../团队作业/插件命令协议.md)
- 移植范围与验收记录：[`团队作业/Day 12-13/NL最小移植范围.md`](../团队作业/Day%2012-13/NL最小移植范围.md)
- 参考插件（未并入）：`nlp_city_editor/`（仅借鉴思路）
