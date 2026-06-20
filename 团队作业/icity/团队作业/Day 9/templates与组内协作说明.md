# templates.json 与组内协作说明

> Day 9 整理：回答 LLM 同学、前端同学如何与 Blender 插件后端对接。

---

## 1. templates.json 是什么？

**用途**：定义「模板 0 / 模板 1」等**一键城市预设**，插件内 **区域 4「模版选择」→ 应用模板** 时读取。

**当前内容**（`config/templates.json`）：

```json
{
  "0": {
    "tree_type": 1,
    "road_texture": 2,
    "bench_type": 1,
    "building_density": "medium",
    "weather": "day"
  },
  "1": {
    "tree_type": 2,
    "road_texture": 1,
    "bench_type": 2,
    "building_density": "high",
    "weather": "night"
  }
}
```

### 字段说明（供 Web 模板库展示）

| 字段 | 类型 | 含义 | 取值 |
|------|------|------|------|
| `tree_type` | int | 树木样式 | 1 或 2 → ICity_Tree 集合索引 |
| `road_texture` | int | 道路纹理类型 | 1 或 2 → 团队/ICity 路面 |
| `bench_type` | int | 座椅样式 | 1 或 2 |
| `building_density` | string | 建筑密度 | `low` / `medium` / `high` |
| `weather` | string | 环境 | `day` / `night`（联动 ICity 灯光模式 + 世界背景） |

**不在 JSON 中的项**：

- **路灯类型**：始终为 ICity 默认路灯（昼夜 Sun 照明）；团队 `Street_Lamp` 仅面板区域 3 手动添加。
- **城市规模 / 建筑样式**：模板应用时使用面板当前值（默认中型 + 类型 1），后续可扩展 JSON 字段。

---

## 2. 与 LLM 同学的关系

### 问：templates.json 是否保持现在这样就好？

**答：作为模板预设，当前版本可以固定使用。** 插件已按此实现并通过 A5 验证。

### 问：是否由 LLM 同学修改 templates.json 来协调？

**答：分两种情况：**

| 场景 | 谁改 | 说明 |
|------|------|------|
| **新增/修改模板 0、1 的配置** | 后端 + 组内共识后改 JSON | 例如新增模板 2、调整密度；改完后同步前端文案 |
| **自然语言控制城市** | **不改 templates.json** | 阶段四用 **命令 JSON 协议**，见下节 |

LLM 模块的职责是：用户中文 → 解析为 **`commands` 数组**，例如：

```json
{
  "commands": [
    { "action": "apply_template", "params": { "template_id": "1" } },
    { "action": "set_weather", "params": { "mode": "night" } }
  ]
}
```

插件侧 `core/command_executor.py` 注册 `action → 处理函数`，由 `operators/nl_execute.py`（待实现）调用。**协议细节阶段四联调前会写进 `插件命令协议.md`（初版）。**

**结论**：templates.json = **静态模板表**；LLM = **动态命令流**。两者配合，但不混为一个文件。

---

## 3. 与前端同学的关系

### 问：前端也需要 templates.json 吗？

**答：需要其内容，但不一定要直接读插件仓库里的文件。**

| 前端用途 | 建议做法 |
|----------|----------|
| Web「模板库」页展示模板 0/1 | 复制本 JSON 或下表为 **展示用配置**；可加中文标题、缩略图 URL |
| 用户点「应用模板 1」 | 若 Web 只展示、实际操作在 Blender，则**无需**前端改 JSON |
| 若未来 Web 远程驱动 Blender | 需与后端约定 API，仍建议 `template_id` 引用同一份编号规则 |

### 建议提供给前端的模板说明表

| 模板 ID | 中文名（示例） | 树 | 路 | 椅 | 密度 | 环境 |
|---------|----------------|----|----|-----|------|------|
| 0 | 日间中等城市 | 1 | 2（团队路面） | 1 | 中 | 白天 |
| 1 | 夜间高密度城市 | 2 | 1 | 2 | 高 | 夜间 |

另需提供（阶段五）：渲染 PNG/MP4、插件名称版本（见主文档 §9.2）。

---

## 4. 同步方式建议（GitHub / 群文档）

1. **本仓库** `config/templates.json` 为插件**唯一数据源**。
2. Day 9 起将本说明 + JSON 发给 LLM / 前端；有变更时在群里 @ 并更新 README。
3. 阶段四前 LLM 同学基于 action 列表草案反提需求，后端在 `command_executor` 注册 handler。

---

## 5. 后续可能扩展（非阶段二范围）

- JSON 增加 `city_scale`、`building_type` 等字段
- 新增模板 `"2"`、`"3"` …
- LLM 输出 `apply_template` 或逐字段 `set_tree_type` 等 action

以上均需**三方简短对齐**后再改 JSON 与文档。
