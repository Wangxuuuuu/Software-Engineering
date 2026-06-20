# ICity / SCG — P0 命令 executor 手动测试脚本
# 用法：Blender → 文本编辑器 → 打开本文件 → 修改下方 RUN（1～6）→ 运行脚本（Alt+P）
# 前提：已 Start ICity，并已「生成基础城市」（用例 6 还需车辆资产）

import bpy

from icity.core.command_executor import execute_commands, list_registered_actions

# ── 改这里：1=变暗  2=白天  3=道路类型1  4=模板0  5=树路椅均1  6=加车 ──
RUN = 1

CASES = {
    1: {
        "name": "将天色变暗（night）",
        "payload": {
            "source": "manual_test",
            "raw_text": "将天色变暗",
            "commands": [
                {"action": "set_environment", "params": {"mode": "night"}},
            ],
            "reply": "已切换夜间环境",
        },
    },
    2: {
        "name": "将天色变为白天（day）",
        "payload": {
            "source": "manual_test",
            "raw_text": "将天色变为白天",
            "commands": [
                {"action": "set_environment", "params": {"mode": "day"}},
            ],
            "reply": "已切换白天环境",
        },
    },
    3: {
        "name": "将道路改为类型 1",
        "payload": {
            "source": "manual_test",
            "raw_text": "将道路改为类型 1",
            "commands": [
                {"action": "set_road_texture", "params": {"type": 1}},
            ],
            "reply": "道路纹理类型 1",
        },
    },
    4: {
        "name": "应用模板 0",
        "payload": {
            "source": "manual_test",
            "raw_text": "应用模板 0",
            "commands": [
                {"action": "apply_template", "params": {"template_id": "0"}},
            ],
            "reply": "已应用模板 0",
        },
    },
    5: {
        "name": "树木、道路和座椅均设为类型 1",
        "payload": {
            "source": "manual_test",
            "raw_text": "将树木、道路和座椅均设为类型 1",
            "commands": [
                {
                    "action": "apply_asset_config",
                    "params": {
                        "tree_type": 1,
                        "road_texture": 1,
                        "bench_type": 1,
                        "regenerate": True,
                    },
                },
            ],
            "reply": "树路椅均为类型 1",
        },
    },
    6: {
        "name": "添加 2 辆车辆（仅车，不含行人）",
        "payload": {
            "source": "manual_test",
            "raw_text": "添加2辆车辆",
            "commands": [
                {"action": "add_dynamic_element", "params": {"type": "car", "count": 2}},
            ],
            "reply": "已添加 2 辆车辆",
        },
    },
}


def run_case(case_id: int) -> None:
    if case_id not in CASES:
        print(f"无效 RUN={case_id}，请使用 1～{len(CASES)}")
        return

    case = CASES[case_id]
    ok, reply, lines = execute_commands(bpy.context, case["payload"])

    print("\n" + "=" * 60)
    print(f"测试：{case['name']}")
    print(f"全部成功：{ok}")
    print(f"reply：{reply}")
    for line in lines:
        print(f"  {line}")
    print("=" * 60)


print("已注册 action：", list_registered_actions())
run_case(RUN)
