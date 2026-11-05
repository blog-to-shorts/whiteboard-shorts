import time
from functools import wraps


def retry(times: int = 3, delay: float = 2.0):
    """API 오류 시 제한적 재시도."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for i in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    if i == times - 1:
                        raise
                    time.sleep(delay * (i + 1))
        return wrapper
    return deco
