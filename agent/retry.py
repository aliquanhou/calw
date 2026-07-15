"""retry — 重试与指数退避机制（v2.1 移植版）。

提供网络请求、API 调用、工具执行失败时的自动重试逻辑，
包含指数退避 + 随机抖动，避免请求风暴。

v2.0 → v2.1 移植：
  - 保留完整的装饰器 + 函数式 + 生成器三重 API
  - 适配 v2.1 的惰性导入原则
  - 与 core.py 的 retry_on_failure 配置集成
"""

from __future__ import annotations

import random
import time
from functools import wraps
from typing import Any, Callable, Generator, Type

# ── 重试配置 ──

DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BASE_DELAY: float = 1.0
DEFAULT_MAX_DELAY: float = 30.0
DEFAULT_JITTER: float = 0.1

RETRYABLE_EXCEPTIONS: list[Type[Exception]] = [
    ConnectionError,
    TimeoutError,
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
]

RETRYABLE_HTTP_CODES: set[int] = {429, 500, 502, 503, 504}

RETRYABLE_KEYWORDS: list[str] = [
    "rate limit", "too many requests",
    "timeout", "timed out",
    "service unavailable", "internal server error", "bad gateway",
    "connection error", "reset by peer", "temporarily unavailable",
    "忙", "超时", "拒绝连接",
]


def is_retryable(e: Exception) -> bool:
    """判断异常是否为可重试的临时性错误。"""
    for exc_type in RETRYABLE_EXCEPTIONS:
        if isinstance(e, exc_type):
            return True
    msg = str(e).lower()
    for keyword in RETRYABLE_KEYWORDS:
        if keyword in msg:
            return True
    return False


def sleep_with_backoff(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> None:
    """指数退避等待。

    等待时间 = min(base_delay * 2^attempt, max_delay) * (1 ± 随机抖动)
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
    """函数重试装饰器。"""
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
            raise RuntimeError("重试逻辑异常") from last_error
        return wrapper
    return decorator


# ── 函数式调用 ──

def with_retry(
    func: Callable, *args: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    retry_on: Callable[[Exception], bool] = is_retryable,
    **kwargs: Any,
) -> Any:
    """调用函数并自动重试。"""
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
    """创建带重试的生成器，适用于流式 API。"""
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
