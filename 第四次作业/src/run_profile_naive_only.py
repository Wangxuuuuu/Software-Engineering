"""仅对朴素算法运行 profile（对应报告「原始代码」性能分析截图）。"""

import profile

import sliding_window_max as swm

# 与 run_profile.py 中朴素规模一致，便于报告对照
SCALE = 30000

if __name__ == "__main__":
    print(f"朴素算法 profile_test(scale={SCALE})")
    profile.run(f"swm.profile_test({SCALE}, use_naive=True)")
