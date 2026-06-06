"""滑动窗口最大值：提供朴素实现与单调队列优化实现。"""

from collections import deque
from typing import List, Optional


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
            print("错误：输入必须是列表类型。")
            return False
        if len(self.nums) == 0:
            print("错误：数组不能为空。")
            return False
        if not isinstance(self.k, int):
            print("错误：窗口大小 k 必须是整数。")
            return False
        if self.k <= 0:
            print("错误：窗口大小 k 必须为正整数。")
            return False
        if self.k > len(self.nums):
            print("错误：窗口大小 k 不能大于数组长度。")
            return False
        for value in self.nums:
            if not isinstance(value, int):
                print("错误：数组元素必须是整数。")
                return False
        return True

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
        index_queue: deque[int] = deque()

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
