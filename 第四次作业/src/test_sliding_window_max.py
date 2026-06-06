"""滑动窗口最大值 — unittest 单元测试。"""

import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

import sliding_window_max as swm
import sliding_window_max_naive as swm_naive


def load_json_cases():
    """从 data/test_cases.json 加载测试用例。"""
    data_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "test_cases.json"
    )
    with open(data_path, encoding="utf-8") as file:
        return json.load(file)


class TestSlidingWindowFunctional(unittest.TestCase):
    """黑盒测试：功能正确性（优化算法）。"""

    def test_cases_from_json(self):
        """遍历 JSON 中全部标准用例。"""
        for case in load_json_cases():
            with self.subTest(description=case["description"]):
                result = swm.unit_test(case["nums"], case["k"], use_naive=False)
                self.assertEqual(result, case["expected"])

    def test_official_example(self):
        """官方示例。"""
        nums = [1, 3, -1, -3, 5, 3, 6, 7]
        expected = [3, 3, 5, 5, 6, 7]
        self.assertEqual(swm.unit_test(nums, 3), expected)

    def test_all_positive(self):
        """全正整数。"""
        self.assertEqual(swm.unit_test([3, 4, 5, 6], 2), [4, 5, 6])

    def test_all_negative(self):
        """全负整数。"""
        self.assertEqual(swm.unit_test([-3, -4, -5], 2), [-3, -4])

    def test_mixed_sign_with_zero(self):
        """正负混合且含 0。"""
        self.assertEqual(swm.unit_test([-2, 0, -1, 3], 2), [0, 0, 3])

    def test_single_element(self):
        """数组长度为 1。"""
        self.assertEqual(swm.unit_test([7], 1), [7])

    def test_duplicate_max_values(self):
        """窗口内存在重复最大值（n=4, k=3 共 2 个窗口）。"""
        self.assertEqual(swm.unit_test([1, 3, 3, 2], 3), [3, 3])


class TestNaiveOptimizedConsistency(unittest.TestCase):
    """黑盒测试：朴素算法与优化算法结果一致。"""

    def test_consistency_on_json_cases(self):
        """JSON 用例上两种实现结果相同。"""
        for case in load_json_cases():
            with self.subTest(description=case["description"]):
                naive = swm.unit_test(case["nums"], case["k"], use_naive=True)
                optimized = swm.unit_test(case["nums"], case["k"], use_naive=False)
                self.assertEqual(naive, optimized)
                self.assertEqual(optimized, case["expected"])

    def test_consistency_random_pattern(self):
        """构造序列上两种实现一致。"""
        nums = [i % 17 - 8 for i in range(50)]
        naive = swm.unit_test(nums, 7, use_naive=True)
        optimized = swm.unit_test(nums, 7, use_naive=False)
        self.assertEqual(naive, optimized)


class TestSlidingWindowValidation(unittest.TestCase):
    """白盒/异常测试：输入合法性校验与错误处理。"""

    def setUp(self):
        self.solver = swm.SlidingWindowMax()

    def test_empty_array(self):
        """空数组应判定非法。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.solver.set_array([], 1)
            self.assertFalse(self.solver.legal)
            self.assertIn("不能为空", mock_out.getvalue())

    def test_k_zero(self):
        """k=0 应判定非法。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.solver.set_array([1, 2], 0)
            self.assertFalse(self.solver.legal)
            self.assertIn("正整数", mock_out.getvalue())

    def test_k_negative(self):
        """k<0 应判定非法。"""
        with patch("sys.stdout", new_callable=StringIO):
            self.solver.set_array([1, 2], -1)
            self.assertFalse(self.solver.legal)

    def test_k_greater_than_n(self):
        """k > len(nums) 应判定非法。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.solver.set_array([1, 2, 3], 4)
            self.assertFalse(self.solver.legal)
            self.assertIn("不能大于", mock_out.getvalue())

    def test_non_list_input(self):
        """非 list 类型应判定非法。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.solver.nums = (1, 2, 3)  # type: ignore
            self.solver.k = 2
            self.assertFalse(self.solver.array_is_legal())
            self.assertIn("列表", mock_out.getvalue())

    def test_non_int_element(self):
        """非 int 元素应判定非法。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.solver.set_array([1, 2.5, 3], 2)
            self.assertFalse(self.solver.legal)
            self.assertIn("整数", mock_out.getvalue())

    def test_non_int_k(self):
        """k 非 int 应判定非法。"""
        with patch("sys.stdout", new_callable=StringIO):
            self.solver.set_array([1, 2, 3], 2.0)  # type: ignore
            self.assertFalse(self.solver.legal)

    def test_solve_returns_none_when_illegal(self):
        """非法输入时 solve 返回 None。"""
        with patch("sys.stdout", new_callable=StringIO):
            self.solver.set_array([], 1)
            self.assertIsNone(self.solver.solve())

    def test_naive_method_returns_none_when_illegal(self):
        """非法输入时朴素方法也返回 None（覆盖错误分支）。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.solver.set_array([], 1)
            self.assertIsNone(self.solver.max_sliding_window_naive())
            self.assertIn("不合法", mock_out.getvalue())


class TestNaiveModule(unittest.TestCase):
    """原始代码文件 sliding_window_max_naive.py 的单元测试。"""

    def test_naive_module_official_example(self):
        """朴素独立模块：官方示例。"""
        solver = swm_naive.SlidingWindowMaxNaive()
        solver.set_array([1, 3, -1, -3, 5, 3, 6, 7], 3)
        self.assertEqual(solver.max_sliding_window(), [3, 3, 5, 5, 6, 7])

    def test_naive_module_invalid_k(self):
        """朴素独立模块：非法 k 返回 None。"""
        solver = swm_naive.SlidingWindowMaxNaive()
        solver.set_array([1, 2], 0)
        self.assertIsNone(solver.max_sliding_window())


def run_test_suite():
    """运行全部测试并返回结果。"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(__import__(__name__)))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    run_test_suite()
