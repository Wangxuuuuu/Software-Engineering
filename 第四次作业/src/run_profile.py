"""Profile 性能分析：对比朴素算法与单调队列优化算法。"""

import os
import profile
import sys
import time

import sliding_window_max as swm


def run_profile(label: str, scale: int, use_naive: bool) -> None:
    """使用 profile 模块对指定规模进行一次性能分析。"""
    mode = "naive" if use_naive else "optimized"
    print("=" * 60)
    print(f"{label} | scale={scale}, mode={mode}")
    print("=" * 60)
    command = f"swm.profile_test({scale}, use_naive={use_naive})"
    profile.run(command)


def run_time_benchmark(scales: list) -> None:
    """使用 time 模块测量墙钟时间，生成可写入报告的对比表。"""
    print("\n" + "=" * 60)
    print("墙钟时间对比（秒）")
    print("=" * 60)
    print(f"{'scale':>10} | {'k':>8} | {'naive(s)':>12} | {'optimized(s)':>14} | {'speedup':>8}")
    print("-" * 60)

    for scale in scales:
        k = min(1000, max(1, scale // 10))
        nums = [i % 100 - 50 for i in range(scale)]

        solver_naive = swm.SlidingWindowMax()
        solver_naive.set_array(nums, k)
        start = time.perf_counter()
        solver_naive.solve(use_naive=True)
        naive_time = time.perf_counter() - start

        solver_opt = swm.SlidingWindowMax()
        solver_opt.set_array(nums, k)
        start = time.perf_counter()
        solver_opt.solve(use_naive=False)
        opt_time = time.perf_counter() - start

        speedup = naive_time / opt_time if opt_time > 0 else float("inf")
        print(
            f"{scale:>10} | {k:>8} | {naive_time:>12.6f} | {opt_time:>14.6f} | {speedup:>8.1f}x"
        )


def main() -> None:
    """默认：先墙钟对比，再分别 profile 两种实现。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base_dir)

    # 墙钟对比规模（可按机器性能调整）
    benchmark_scales = [5000, 10000, 20000, 50000]
    run_time_benchmark(benchmark_scales)

    # profile 分析规模：朴素用较小规模，优化用较大规模
    naive_scale = 30000
    optimized_scale = 500000

    print("\n提示：朴素算法 profile 规模较小，优化算法规模较大。")
    print("若运行过慢，可在本脚本中调小 naive_scale / optimized_scale。\n")

    run_profile("朴素算法 profile 分析", naive_scale, use_naive=True)
    run_profile("优化算法 profile 分析", optimized_scale, use_naive=False)


if __name__ == "__main__":
    main()
