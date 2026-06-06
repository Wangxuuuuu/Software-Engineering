# 软件工程第四次个人作业 — 滑动窗口最大值

**学号：** 2312166  
**姓名：** 王旭  
**题目：** 软件编码实现、分析和测试

---

## 目录说明

| 路径 | 说明 |
|------|------|
| `2312166_王旭_第四次个人作业.pdf` | 实验报告 |
| `src/` | Python 源代码与测试脚本 |
| `data/` | 测试数据与测试用例表 |
| `my_coverage_result/` | 代码覆盖率 HTML 报告（由 `coverage` 生成） |

### `src/` 主要文件

- `sliding_window_max.py` — 主程序（单调队列优化 + 内置朴素算法）
- `sliding_window_max_naive.py` — 原始实现（对比基线）
- `test_sliding_window_max.py` — unittest 单元测试
- `run_pylint.py` / `run_profile*.py` / `run_coverage.py` — 静态分析、性能与覆盖率复现脚本
- `before_pylint/` — Pylint 修复前代码（报告对比用）

### `data/` 主要文件

- `test_cases.json` — 标准测试用例（含题目示例）
- `test_case_table.md` — 测试用例说明表

---

## 覆盖率报告查看

在浏览器中打开：

**`my_coverage_result/index.html`**

可查看各模块语句覆盖率；点击文件名可进入逐行覆盖详情（如 `sliding_window_max_py.html`）。
