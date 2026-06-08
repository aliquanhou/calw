"""
重试与指数退避机制

提供网络请求、API 调用、工具执行失败时的自动重试逻辑，
包含指数退避 + 随机抖动，避免请求风暴。
"""

from __future__ import annotations

import random
import time
from functools import wraps
from typing import Any, Callable, Generator, Type

# ── 重试配置 ──

DEFAULT_MAX_RETRIES: int = 3          # 最大重试次数
DEFAULT_BASE_DELAY: float = 1.0       # 初始延迟（秒）
DEFAULT_MAX_DELAY: float = 30.0       # 最大延迟上限
DEFAULT_JITTER: float = 0.1           # 随机抖动比例（±10%）

# 需要重试的临时性异常类型
RETRYABLE_EXCEPTIONS: list[Type[Exception]] = [
    ConnectionError,
    TimeoutError,
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
]

# 需要重试的 HTTP 状态码（由 web 工具使用）
RETRYABLE_HTTP_CODES: set[int] = {429, 500, 502, 503, 504}

# 需要重试的错误信息关键词
RETRYABLE_KEYWORDS: list[str] = [
    "rate limit", "too many requests",
    "timeout", "timed out",
    "service unavailable", "internal server error", "bad gateway",
    "connection error", "reset by peer", "temporarily unavailable",
    "忙", "超时", "拒绝连接",
]


def is_retryable(e: Exception) -> bool:
    """判断异常是否为可重试的临时性错误

    先检查异常类型是否在预定义列表中，
    再通过错误信息关键词匹配进行二次判断。

    Args:
        e: 要检查的异常对象

    Returns:
        是否为可重试的临时性错误
    """
    for exc_type in RETRYABLE_EXCEPTIONS:
        if isinstance(e, exc_type):
            return True
    # 通过错误信息关键词匹配常见库的错误
    msg = str(e).lower()
    for keyword in RETRYABLE_KEYWORDS:
        if keyword in msg:
            return True
    return False


def sleep_with_backoff(attempt: int, base_delay: float = DEFAULT_BASE_DELAY,
                       max_delay: float = DEFAULT_MAX_DELAY) -> None:
    """指数退避等待

    等待时间 = min(base_delay * 2^attempt, max_delay) * (1 ± 随机抖动)

    Args:
        attempt: 当前重试次数（从 0 开始）
        base_delay: 基础延迟秒数
        max_delay: 最大延迟秒数上限
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = delay * DEFAULT_JITTER * random.uniform(-1, 1)
    time.sleep(max(0.1, delay + jitter))


# ── 装饰器形式 ──

def retryable(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    retry_on: Callable[[Exception], bool] = is_retryable,
) -> Callable:
    """函数重试装饰器

    当函数抛出可重试异常时，自动进行指数退避重试。

    Args:
        max_retries: 最大重试次数，默认 3
        base_delay: 初始退避延迟秒数，默认 1
        max_delay: 最大延迟上限秒数，默认 30
        retry_on: 自定义异常可重试判断函数

    Returns:
        装饰器

    Raises:
        最后一次尝试时抛出的异常（如果全部失败）

    使用示例:
        @retryable(max_retries=3)
        def call_api() -> dict:
            return requests.get("https://api.example.com").json()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries and retry_on(e):
                        sleep_with_backoff(attempt, base_delay, max_delay)
                        continue
                    raise
            # 不应到达此处，但保持类型安全
            raise RuntimeError("重试逻辑异常") from last_error
        return wrapper
    return decorator


# ── 函数式调用 ──

def with_retry(func: Callable, *args: Any,
               max_retries: int = DEFAULT_MAX_RETRIES,
               base_delay: float = DEFAULT_BASE_DELAY,
               max_delay: float = DEFAULT_MAX_DELAY,
               retry_on: Callable[[Exception], bool] = is_retryable,
               **kwargs: Any) -> Any:
    """调用函数并自动重试，返回函数结果

    适用于非生成器函数的重试。如果是生成器函数，请使用 retry_generator。

    Args:
        func: 要调用的函数
        *args: 传递给函数的位置参数
        max_retries: 最大重试次数
        base_delay: 初始退避延迟
        max_delay: 最大延迟上限
        retry_on: 自定义异常可重试判断函数
        **kwargs: 传递给函数的关键字参数

    Returns:
        函数执行结果

    Raises:
        最后一次尝试时抛出的异常（如果全部失败）
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries and retry_on(e):
                sleep_with_backoff(attempt, base_delay, max_delay)
                continue
            raise
    raise RuntimeError("重试逻辑异常") from last_error


# ── 生成器重试（用于流式 API）──

def retry_generator(
    factory: Callable[[], Any],
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    retry_on: Callable[[Exception], bool] = is_retryable,
) -> Generator[Any, None, None]:
    """创建带重试的生成器

    适用于流式 API（如 SSE、流式 LLM 响应）的重试。

    Args:
        factory: 返回可迭代对象的工厂函数
        max_retries: 最大重试次数
        base_delay: 初始退避延迟
        max_delay: 最大延迟上限
        retry_on: 自定义异常可重试判断函数

    Yields:
        工厂函数生成的数据项

    使用示例:
        for chunk in retry_generator(lambda: client.stream(...)):
            yield chunk
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            yield from factory()
            return
        except Exception as e:
            last_error = e
            if attempt < max_retries and retry_on(e):
                sleep_with_backoff(attempt, base_delay, max_delay)
                continue
            raise
    raise RuntimeError("重试逻辑异常") from last_error
