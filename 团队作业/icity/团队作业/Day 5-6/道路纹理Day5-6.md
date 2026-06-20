# Day 5-6：道路纹理（阶段二 §5.1.1）

> 对应 `待办工作流程及时间线.md` §5.1.1，验收 **A3**（**已通过**功能验证）。  
> 机制与验证详见 **[Day5-6工作总结.md](./Day5-6工作总结.md)**。

## 贴图参考（必读）

### 作业要新增什么？

- 老师要求：**至少 1 种** 新 2D 道路贴图 + 能在场景里 **替换**。
- **只需 1 张「颜色贴图」（BaseColor）** 即可答辩；不必做完整 PBR 五件套。
- **Material** 是 Blender 里的材质球，由代码用贴图自动拼出，不是你要单独下载的文件类型。

### PBR 是什么？我们代码在干什么？

**PBR** = 用多张图（Color / Normal / Roughness / Height…）拼出更真实的路面。  
`assets_manager.py` 在 **没有** 团队 `road_typeN.jpg` 时会 **回退 ICity 完整 PBR**（模拟官方路面）。  
**有** `road_typeN.jpg` 时 **只用这一张 BaseColor**，足够满足作业「新增 2D 资产」。

| 贴图角色 | 作用 | 作业是否必须 |
|----------|------|--------------|
| **BaseColor**（`road_typeN.jpg`） | 路面颜色与花纹，肉眼差异最大 | **必须（团队新增）** |
| Normal / Roughness / Height | 细节、反光、凹凸 | 可选，代码回退 ICity 时有 |

### 换图不改代码（固定文件名）

| 文件 | 用途 |
|------|------|
| `assets/team/textures/road_type1.jpg` | 道路 **类型1** BaseColor |
| `assets/team/textures/road_type2.jpg` | 道路 **类型2** BaseColor（**团队新增主资产**，已放入候选图） |

后续换路面：**只替换同名 jpg/png 文件** → 重载插件或重新「应用道路纹理」。  
若文件不存在，该类型自动回退 ICity PBR。

> 旧占位文件 `Road 4 clean_Normal.jpg` / `_Height.jpg` 可删除，不再使用。

---

## 已完成项

- [x] 团队主贴图 `road_type2.jpg`（BaseColor）
- [x] `assets_manager.py`：`TEAM_ROAD_BASECOLOR` + ICity PBR 回退
- [x] `set_road_texture` / `scg.apply_road_texture` / 面板区域 2
- [x] 材质预览下类型1/2 可切换（已验证）

## 使用

1. Start → 生成基础城市  
2. 视口 **材质预览**  
3. 区域 2：选类型 → **应用道路纹理**  
4. A3：类型1 vs 类型2 截图 → `团队作业/screenshots/`

## 代码入口

| 入口 | 说明 |
|------|------|
| `TEAM_ROAD_BASECOLOR` | 固定路径 `road_type1/2.jpg` |
| `set_road_texture(n)` | → `Road 2.nodes["Road"].inputs[2]` |

## 相关文档

- [Day 2-3/资产机制说明.md](../Day%202-3/资产机制说明.md)
- [Day 4/阶段一复盘-ICity复用与新写.md](../Day%204/阶段一复盘-ICity复用与新写.md)

## 下一步

§5.1.2 路灯（Day 6-7）→ `assets/team/models/street_light.blend`
