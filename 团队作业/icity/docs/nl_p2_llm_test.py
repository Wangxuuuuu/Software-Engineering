# ICity / SCG — P2 LLM 联调手动测试
# 用法：Blender → 文本编辑器 → 打开本文件 → 配置 API Key → 修改 RUN → Alt+P
#
# 前提：
#   1. Reload Scripts
#   2. 编辑→偏好设置→插件→ICity → 「Smart City · 自然语言 LLM」填写 API Key
#   3. 已 Start ICity 并生成基础城市
#   4. 区域 7 开启 LLM 开关

import bpy

from icity.core.nl_intent_engine import parse_nl_input
from icity.core.command_executor import execute_commands
from icity.scg_nl_preferences import get_nl_settings, sync_scene_from_disk

# 0=仅测解析  1～5=A6五条（解析+执行）  6=组合句「变暗并加2辆车」
RUN = 0

CASES = {
    1: "将天色变暗",
    2: "将道路改为类型 1",
    3: "应用模板 0",
    4: "将树木、道路和座椅均设为类型 1",
    5: "添加2辆车辆",
    6: "将天色变暗并添加2辆车辆",
}


def _api_ready() -> bool:
    sync_scene_from_disk(bpy.context.scene)
    settings = get_nl_settings()
    key = settings.get("api_key", "")
    if not key:
        print("请先在区域 7「LLM API 配置」填写 API Key，并点「保存到本地」")
        return False
    print(f"提供商={settings.get('provider')}  model={settings.get('model')}")
    return True


def run_parse(text: str) -> dict:
    payload = parse_nl_input(text, use_llm=True)
    print("\n" + "=" * 60)
    print(f"输入：{text}")
    print(f"source：{payload.get('source')}")
    print(f"commands：{payload.get('commands')}")
    print(f"reply：{payload.get('reply')}")
    print("=" * 60)
    return payload


def run_full(text: str) -> bool:
    payload = run_parse(text)
    if not payload.get("commands"):
        return False
    ok, reply, lines = execute_commands(bpy.context, payload)
    print(f"执行成功：{ok}")
    print(f"reply：{reply}")
    for line in lines:
        print(f"  {line}")
    return ok


def main():
    if not _api_ready():
        return

    bpy.context.scene.scg_use_llm = True

    if RUN == 0:
        for text in CASES.values():
            run_parse(text)
        return

    if RUN not in CASES:
        print(f"无效 RUN={RUN}，请使用 0 或 1～{len(CASES)}")
        return

    run_full(CASES[RUN])


main()
