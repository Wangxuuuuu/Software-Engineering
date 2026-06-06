"""优化前的朴素实现（暴力枚举每个窗口的最大值）。"""

from typing import List, Optional


class SlidingWindowMaxNaive:
    """滑动窗口最大值 — 朴素版本，仅用于对比基线。"""

    def __init__(self) -> None:
        self.nums: List[int] = []
        self.k: int = 0

    def set_array(self, nums: List[int], k: int) -> None:
        self.nums = nums
        self.k = k

    def max_sliding_window(self) -> Optional[List[int]]:
        """对每个窗口暴力求最大值，时间复杂度 O(n*k)。"""
        n = len(self.nums)
        if self.k <= 0 or self.k > n:
            return None

        result: List[int] = []
        for start in range(n - self.k + 1):
            window_max = self.nums[start]
            for idx in range(start + 1, start + self.k):
                if self.nums[idx] > window_max:
                    window_max = self.nums[idx]
            result.append(window_max)
        return result
