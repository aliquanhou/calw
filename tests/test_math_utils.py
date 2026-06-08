"""
math_utils 模块的单元测试
"""

from __future__ import annotations

import unittest

from agent.utils.math_utils import (
    average,
    clamp,
    fibonacci,
    is_prime,
    median,
    normalize,
    percentage,
    round_to,
    standard_deviation,
)


class TestMathUtils(unittest.TestCase):
    """数学工具函数测试"""

    def test_clamp_within_range(self):
        """测试值在范围内"""
        self.assertEqual(clamp(5, 0, 10), 5)

    def test_clamp_below_min(self):
        """测试值低于最小值"""
        self.assertEqual(clamp(-5, 0, 10), 0)

    def test_clamp_above_max(self):
        """测试值高于最大值"""
        self.assertEqual(clamp(15, 0, 10), 10)

    def test_clamp_invalid_range(self):
        """测试无效范围"""
        with self.assertRaises(ValueError):
            clamp(5, 10, 0)

    def test_round_to_zero(self):
        """测试四舍五入到整数"""
        self.assertEqual(round_to(3.7), 4)
        self.assertEqual(round_to(3.4), 3)

    def test_round_to_precision(self):
        """测试四舍五入到指定精度"""
        self.assertEqual(round_to(3.14159, 2), 3.14)
        self.assertEqual(round_to(3.14159, 4), 3.1416)

    def test_percentage_normal(self):
        """测试正常百分比计算"""
        self.assertEqual(percentage(25, 100), "25.00%")
        self.assertEqual(percentage(1, 3), "33.33%")

    def test_percentage_zero_total(self):
        """测试总数为 0"""
        with self.assertRaises(ZeroDivisionError):
            percentage(10, 0)

    def test_average_normal(self):
        """测试平均值计算"""
        self.assertEqual(average([1, 2, 3, 4, 5]), 3.0)
        self.assertEqual(average([10]), 10.0)

    def test_average_empty(self):
        """测试空序列"""
        with self.assertRaises(ValueError):
            average([])

    def test_median_odd(self):
        """测试奇数个数的中位数"""
        self.assertEqual(median([1, 3, 5]), 3)

    def test_median_even(self):
        """测试偶数个数的中位数"""
        self.assertEqual(median([1, 2, 3, 4]), 2.5)

    def test_median_empty(self):
        """测试空序列中位数"""
        with self.assertRaises(ValueError):
            median([])

    def test_standard_deviation(self):
        """测试标准差计算"""
        result = standard_deviation([1, 2, 3, 4, 5])
        self.assertAlmostEqual(result, 1.414, places=3)

    def test_standard_deviation_insufficient_data(self):
        """测试数据不足"""
        with self.assertRaises(ValueError):
            standard_deviation([1])

    def test_is_prime_small(self):
        """测试小素数"""
        self.assertTrue(is_prime(2))
        self.assertTrue(is_prime(3))
        self.assertTrue(is_prime(5))
        self.assertTrue(is_prime(7))

    def test_is_prime_non_prime(self):
        """测试非素数"""
        self.assertFalse(is_prime(0))
        self.assertFalse(is_prime(1))
        self.assertFalse(is_prime(4))
        self.assertFalse(is_prime(9))

    def test_is_prime_large(self):
        """测试大素数"""
        self.assertTrue(is_prime(97))
        self.assertTrue(is_prime(7919))

    def test_is_prime_negative(self):
        """测试负数"""
        with self.assertRaises(ValueError):
            is_prime(-5)

    def test_fibonacci_normal(self):
        """测试斐波那契数列"""
        self.assertEqual(fibonacci(0), [])
        self.assertEqual(fibonacci(1), [0])
        self.assertEqual(fibonacci(5), [0, 1, 1, 2, 3])
        self.assertEqual(fibonacci(10), [0, 1, 1, 2, 3, 5, 8, 13, 21, 34])

    def test_fibonacci_negative(self):
        """测试负数项数"""
        with self.assertRaises(ValueError):
            fibonacci(-1)

    def test_normalize_basic(self):
        """测试基本归一化"""
        result = normalize([1, 2, 3, 4, 5])
        self.assertEqual(result, [0, 0.25, 0.5, 0.75, 1])

    def test_normalize_empty(self):
        """测试空序列归一化"""
        with self.assertRaises(ValueError):
            normalize([])

    def test_normalize_same_values(self):
        """测试所有值相同"""
        with self.assertRaises(ValueError):
            normalize([5, 5, 5])

    def test_normalize_custom_range(self):
        """测试自定义范围归一化"""
        result = normalize([10, 20, 30], min_val=0, max_val=50)
        self.assertEqual(result, [0.2, 0.4, 0.6])


if __name__ == "__main__":
    unittest.main()
