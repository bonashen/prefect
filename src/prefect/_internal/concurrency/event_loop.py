"""
Utilities for working with asynchronous event loops.
"""

import asyncio
import concurrent.futures
import functools
from typing import Callable, Optional, TypeVar

from typing_extensions import ParamSpec

P = ParamSpec("P")
T = TypeVar("T")


def get_running_loop() -> Optional[asyncio.BaseEventLoop]:
    """
    Get the current running loop.

    Returns `None` if there is no running loop.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def run_in_loop_thread(
    __loop: asyncio.AbstractEventLoop,
    __fn: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs
) -> T:
    """
    Run a synchronous call in event loop's thread from another thread.
    """
    future = concurrent.futures.Future()

    @functools.wraps(__fn)
    def wrapper() -> None:
        try:
            future.set_result(__fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
            if not isinstance(exc, Exception):
                raise

    __loop.call_soon_threadsafe(wrapper)
    return future.result()
