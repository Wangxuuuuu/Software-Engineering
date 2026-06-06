"""滑动窗口最大值：提供朴素实现与单调队列优化实现。"""

from collections import deque
from typing import Deque, List, Optional


class SlidingWindowMax:
    """滑动窗口最大值求解器。"""

    def __init__(self) -> None:
        """初始化数组与窗口大小。"""
        self.nums: List[int] = []
        self.k: int = 0
        self.legal: bool = False

    def set_array(self, nums: List[int], k: int) -> None:
        """直接设置待处理数组与窗口大小。"""
        self.nums = nums
        self.k = k
        self.legal = self.array_is_legal()

    def array_is_legal(self) -> bool:
        """判断输入数组与窗口大小是否合法。"""
        if not isinstance(self.nums, list):
            message = "错误：输入必须是列表类型。"
        elif len(self.nums) == 0:
            message = "错误：数组不能为空。"
        elif not isinstance(self.k, int):
            message = "错误：窗口大小 k 必须是整数。"
        elif self.k <= 0:
            message = "错误：窗口大小 k 必须为正整数。"
        elif self.k > len(self.nums):
            message = "错误：窗口大小 k 不能大于数组长度。"
        elif not all(isinstance(value, int) for value in self.nums):
            message = "错误：数组元素必须是整数。"
        else:
            return True
        print(message)
        return False

    def max_sliding_window_naive(self) -> Optional[List[int]]:
        """朴素实现：对每个窗口暴力求最大值。时间复杂度 O(n*k)。"""
        if not self.legal:
            print("错误：输入不合法，无法求解。")
            return None

        n = len(self.nums)
        result: List[int] = []
        for start in range(n - self.k + 1):
            window_max = self.nums[start]
            for idx in range(start + 1, start + self.k):
                if self.nums[idx] > window_max:
                    window_max = self.nums[idx]
            result.append(window_max)
        return result

    def max_sliding_window(self) -> Optional[List[int]]:
        """优化实现：单调双端队列。时间复杂度 O(n)。"""
        if not self.legal:
            print("错误：输入不合法，无法求解。")
            return None

        n = len(self.nums)
        result: List[int] = []
        index_queue: Deque[int] = deque()

        for idx in range(n):
            while index_queue and self.nums[index_queue[-1]] <= self.nums[idx]:
                index_queue.pop()
            index_queue.append(idx)

            if index_queue[0] <= idx - self.k:
                index_queue.popleft()

            if idx >= self.k - 1:
                result.append(self.nums[index_queue[0]])

        return result

    def solve(self, use_naive: bool = False) -> Optional[List[int]]:
        """统一求解入口，便于扩展不同算法实现。"""
        if use_naive:
            return self.max_sliding_window_naive()
        return self.max_sliding_window()


def unit_test(nums: List[int], k: int, use_naive: bool = False) -> Optional[List[int]]:
    """供单元测试调用的辅助函数。"""
    solver = SlidingWindowMax()
    solver.set_array(nums, k)
    return solver.solve(use_naive=use_naive)


def profile_test(scale: int, use_naive: bool = False) -> None:
    """供性能分析调用的辅助函数（跳过校验以聚焦核心算法）。"""
    nums = [i % 100 - 50 for i in range(scale)]
    k = min(1000, max(1, scale // 10))
    solver = SlidingWindowMax()
    solver.nums = nums
    solver.k = k
    solver.legal = True
    solver.solve(use_naive=use_naive)


def main() -> None:
    """主函数：演示官方示例。"""
    example_nums = [1, 3, -1, -3, 5, 3, 6, 7]
    example_k = 3

    solver = SlidingWindowMax()
    solver.set_array(example_nums, example_k)

    naive_result = solver.solve(use_naive=True)
    optimized_result = solver.solve(use_naive=False)

    print("输入 nums:", example_nums)
    print("窗口大小 k:", example_k)
    print("朴素算法结果:", naive_result)
    print("优化算法结果:", optimized_result)


if __name__ == "__main__":
    main()
