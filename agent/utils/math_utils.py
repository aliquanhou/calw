"""
数学工具模块

提供常用的数学计算、统计和验证工具函数。
"""

from __future__ import annotations

import math
import statistics
from typing import Optional, Sequence


def clamp(value: float, min_value: float, max_value: float) -> float:
    """将值限制在 [min_value, max_value] 范围内

    Args:
        value: 原始值
        min_value: 最小值
        max_value: 最大值

    Returns:
        限制后的值

    Raises:
        ValueError: 最小值大于最大值
    """
    if min_value > max_value:
        raise ValueError(f"最小值 ({min_value}) 不能大于最大值 ({max_value})")
    return max(min_value, min(value, max_value))


def round_to(value: float, precision: int = 0) -> float:
    """四舍五入到指定精度

    Args:
        value: 要舍入的值
        precision: 小数位数，默认 0

    Returns:
        舍入后的值
    """
    return round(value, precision)


def percentage(value: float, total: float, precision: int = 2) -> str:
    """计算百分比并格式化为字符串

    Args:
        value: 部分值
        total: 总值
        precision: 小数位数，默认 2

    Returns:
        格式化后的百分比字符串，如 "45.50%"

    Raises:
        ZeroDivisionError: total 为 0
    """
    if total == 0:
        raise ZeroDivisionError("总数不能为 0，无法计算百分比")
    percent = (value / total) * 100
    return f"{percent:.{precision}f}%"


def average(numbers: Sequence[float]) -> float:
    """计算平均值

    Args:
        numbers: 数值序列

    Returns:
        算术平均值

    Raises:
        ValueError: 序列为空
    """
    if not numbers:
        raise ValueError("无法计算空序列的平均值")
    return sum(numbers) / len(numbers)


def median(numbers: Sequence[float]) -> float:
    """计算中位数

    Args:
        numbers: 数值序列

    Returns:
        中位数值

    Raises:
        ValueError: 序列为空
    """
    if not numbers:
        raise ValueError("无法计算空序列的中位数")
    return statistics.median(numbers)


def standard_deviation(numbers: Sequence[float], ddof: int = 0) -> float:
    """计算标准差

    Args:
        numbers: 数值序列
        ddof: 自由度修正（0=总体标准差，1=样本标准差）

    Returns:
        标准差

    Raises:
        ValueError: 数据点不足
    """
    if len(numbers) < 2:
        raise ValueError(f"至少需要 2 个数据点，当前只有 {len(numbers)} 个")
    return statistics.stdev(numbers, xbar=None) if ddof == 1 else statistics.pstdev(numbers)


def is_prime(n: int) -> bool:
    """判断是否为素数

    Args:
        n: 要判断的正整数

    Returns:
        是否为素数

    Raises:
        ValueError: n 小于 0
    """
    if n < 0:
        raise ValueError(f"不能为负数: {n}")
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(math.sqrt(n)) + 1, 2):
        if n % i == 0:
            return False
    return True


def fibonacci(n: int) -> list[int]:
    """生成斐波那契数列前 n 项

    Args:
        n: 项数

    Returns:
        斐波那契数列列表

    Raises:
        ValueError: n 小于 0
    """
    if n < 0:
        raise ValueError(f"项数不能为负数: {n}")
    if n == 0:
        return []
    if n == 1:
        return [0]

    result = [0, 1]
    for _ in range(2, n):
        result.append(result[-1] + result[-2])
    return result


def normalize(values: Sequence[float], min_val: Optional[float] = None, max_val: Optional[float] = None) -> list[float]:
    """将数值序列归一化到 [0, 1] 范围

    Args:
        values: 原始数值序列
        min_val: 自定义最小值（None 则自动计算）
        max_val: 自定义最大值（None 则自动计算）

    Returns:
        归一化后的数值列表

    Raises:
        ValueError: 序列为空或所有值相同
    """
    if not values:
        raise ValueError("无法归一化空序列")

    min_v = min(values) if min_val is None else min_val
    max_v = max(values) if max_val is None else max_val

    if max_v == min_v:
        raise ValueError("所有值相同，无法归一化")

    return [(v - min_v) / (max_v - min_v) for v in values]
