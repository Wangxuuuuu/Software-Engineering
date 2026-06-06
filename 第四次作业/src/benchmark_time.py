"""墙钟时间对比，输出可保存到 fig/对应txt(终端输出)/。"""

import time

import sliding_window_max as swm


def main() -> None:
    scales = [5000, 10000, 20000, 50000]
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


if __name__ == "__main__":
    main()
