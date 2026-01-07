# timing_decorator.py  (replace the old version)
import time
import functools
from typing import Callable, Any, Optional, TypeVar, cast
from app_logger import logger   # <-- new import

F = TypeVar("F", bound=Callable[..., Any])

def timed(label: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator that measures execution time and logs it at DEBUG level.
    The message goes to the file handler only (memory handler filters it out).
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.time() - start
                tag = label or func.__qualname__
                # DEBUG → file only, not UI
                logger.debug("[%(tag)s] took %(elapsed).4f s",
                             {"tag": tag, "elapsed": elapsed})
        return cast(F, wrapper)
    return decorator
