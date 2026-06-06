"""阶段一：验证朴素算法与优化算法结果一致。"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sliding_window_max as swm


def main() -> None:
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "test_cases.json")
    with open(data_path, encoding="utf-8") as file:
        cases = json.load(file)

    passed = 0
    for index, case in enumerate(cases, 1):
        naive = swm.unit_test(case["nums"], case["k"], use_naive=True)
        optimized = swm.unit_test(case["nums"], case["k"], use_naive=False)
        ok = naive == case["expected"] and optimized == case["expected"]
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"[{status}] Case {index} ({case['description']})")
        if not ok:
            print(f"  expected={case['expected']}, naive={naive}, opt={optimized}")

    print(f"\nTotal: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
