"""仅对优化算法运行 profile（对应报告「优化后」性能分析截图）。"""

import profile

import sliding_window_max as swm

# 与 run_profile.py 中优化规模一致
SCALE = 500000

if __name__ == "__main__":
    print(f"优化算法 profile_test(scale={SCALE})")
    profile.run(f"swm.profile_test({SCALE}, use_naive=False)")
