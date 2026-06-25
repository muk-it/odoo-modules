from __future__ import annotations

from collections.abc import Callable


def monkey_patch(cls: type) -> Callable:
    """Build a decorator that binds the decorated function onto ``cls``.

    The replaced attribute is kept on the new function as ``super`` to delegate.
    """

    def decorate(func: Callable) -> Callable:
        func.super = getattr(cls, func.__name__, None)
        setattr(cls, func.__name__, func)
        return func

    return decorate
