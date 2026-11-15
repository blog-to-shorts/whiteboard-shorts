"""API 호출 재시도 (지수 백오프). 마지막 실패는 그대로 예외를 올린다."""
import functools
import time

from .logger import log


class NoRetryError(RuntimeError):
    """다시 시도해도 결과가 같은 오류(인증·권한·요금제 등). 즉시 중단한다."""


def retry(times: int = 3, base_delay: float = 2.0):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except NoRetryError:
                    raise
                except Exception as e:  # noqa: BLE001
                    if attempt == times:
                        raise
                    wait = base_delay * 2 ** (attempt - 1)
                    log.warning(f"{fn.__name__} 실패({attempt}/{times}): {e} → {wait:.0f}초 후 재시도")
                    time.sleep(wait)
        return wrapper
    return deco