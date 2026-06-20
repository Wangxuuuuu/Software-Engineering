# P1 离线解析自测（无需 Blender）
# 用法：在项目根目录执行  python docs/nl_p1_offline_test.py

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.nl_intent_engine import offline_parse, parse_nl_input

A6_CASES = [
    ("将天色变暗", "set_environment", {"mode": "night"}),
    ("将道路改为类型 1", "set_road_texture", {"type": 1}),
    ("应用模板 0", "apply_template", {"template_id": "0"}),
    ("将树木、道路和座椅均设为类型 1", "apply_asset_config", None),
    ("添加2辆车辆", "add_dynamic_element", {"type": "car", "count": 2}),
]

EXTRA_CASES = [
    ("将天色变为白天", "set_environment", {"mode": "day"}),
    ("切换为雨天模式", "set_environment", {"mode": "rainy"}),
]


def check_case(text, expect_action, expect_params_subset):
    result = offline_parse(text)
    if not result or not result.get("commands"):
        return False, "offline_parse 返回空"
    cmd = result["commands"][0]
    if cmd["action"] != expect_action:
        return False, f"action={cmd['action']}"
    if expect_params_subset:
        for k, v in expect_params_subset.items():
            if cmd.get("params", {}).get(k) != v:
                return False, f"params[{k}]={cmd['params'].get(k)}"
    return True, result.get("reply", "")


def main():
    failed = 0
    print("=== P1 离线规则（A6 + 扩展）===\n")
    for text, action, params in A6_CASES + EXTRA_CASES:
        ok, msg = check_case(text, action, params)
        tag = "OK" if ok else "FAIL"
        print(f"  [{tag}] {text}")
        if not ok:
            print(f"        -> {msg}")
            failed += 1

    print("\n=== 未知指令回退 ===")
    unknown = parse_nl_input("随便说点什么")
    print(f"  source={unknown.get('source')}")
    print(f"  commands={unknown.get('commands')}")
    print(f"  reply={unknown.get('reply')}")

    print("\n" + "=" * 40)
    if failed:
        print(f"失败 {failed} 条")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
