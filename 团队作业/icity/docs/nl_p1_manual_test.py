# ICity / SCG — P1 自然语言全链路手动测试（解析 + 执行）
# 用法：Blender → 文本编辑器 → 打开本文件 → 修改 RUN（1～7 或 0=全部）→ 运行（Alt+P）
# 前提：已 Start ICity，并已「生成基础城市」（用例 7 还需车辆资产）
# 注意：LLM 开关关闭（scg_use_llm=False）时走离线规则

import bpy

from icity.core.nl_intent_engine import parse_nl_input
from icity.core.command_executor import execute_commands

# 0=全部  1～5=A6五条  6=白天  7=雨天
RUN = 1

CASES = {
    1: "将天色变暗",
    2: "将道路改为类型 1",
    3: "应用模板 0",
    4: "将树木、道路和座椅均设为类型 1",
    5: "添加2辆车辆",
    6: "将天色变为白天",
    7: "切换为雨天模式",
}


def run_one(text: str) -> bool:
    scene = bpy.context.scene
    scene.scg_use_llm = False
    scene.scg_nl_input_text = text

    payload = parse_nl_input(text, use_llm=False)
    print("\n" + "=" * 60)
    print(f"输入：{text}")
    print(f"source：{payload.get('source')}")
    print(f"commands：{payload.get('commands')}")
    print(f"reply：{payload.get('reply')}")

    if not payload.get("commands"):
        print("解析失败，跳过执行")
        return False

    ok, reply, lines = execute_commands(bpy.context, payload)
    print(f"执行成功：{ok}")
    print(f"reply：{reply}")
    for line in lines:
        print(f"  {line}")
    print("=" * 60)
    return ok


def main():
    if RUN == 0:
        ids = sorted(CASES.keys())
    elif RUN in CASES:
        ids = [RUN]
    else:
        print(f"无效 RUN={RUN}，请使用 0 或 1～{len(CASES)}")
        return

    passed = 0
    for case_id in ids:
        if run_one(CASES[case_id]):
            passed += 1

    print(f"\n完成：{passed}/{len(ids)} 条执行成功")


main()
