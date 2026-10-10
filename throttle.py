"""登录限流。

私有工具不需要这个，开源之后需要：任何人读一遍代码就知道登录接口长什么样，
没有限流的话爆破只是时间问题。

实现是**进程内的滑动窗口**，因为本系统按设计单进程运行（waitress 或 gunicorn -w 1），
不值得为它引入 Redis。真要横向扩成多进程多副本，把这个模块换成共享存储即可，
调用方（views/auth.py）不用动。
"""
import threading
import time
from collections import defaultdict, deque

from config import LOGIN_LOCKOUT, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW

_lock = threading.Lock()
_failures: dict[str, deque] = defaultdict(deque)
_locked_until: dict[str, float] = {}


def _now() -> float:
    return time.monotonic()


def _prune(now: float) -> None:
    """把过期的记录清掉，否则长期运行会一直涨内存。"""
    for key in list(_failures):
        window = _failures[key]
        while window and now - window[0] > LOGIN_WINDOW:
            window.popleft()
        if not window:
            del _failures[key]
    for key in list(_locked_until):
        if _locked_until[key] <= now:
            del _locked_until[key]


def check(key: str) -> tuple[bool, int]:
    """这个 key 现在允许尝试吗？返回 (是否允许, 还需等待的秒数)。"""
    now = _now()
    with _lock:
        _prune(now)
        until = _locked_until.get(key)
        if until and until > now:
            return False, int(until - now) + 1
        return True, 0


def record_failure(key: str) -> bool:
    """记一次失败。返回 True 表示这一下刚好触发了锁定。"""
    now = _now()
    with _lock:
        _prune(now)
        window = _failures[key]
        window.append(now)
        if len(window) >= LOGIN_MAX_ATTEMPTS:
            _locked_until[key] = now + LOGIN_LOCKOUT
            window.clear()
            return True
        return False


def remaining(key: str) -> int:
    """还允许失败几次，用于给用户提示。"""
    now = _now()
    with _lock:
        _prune(now)
        if _locked_until.get(key, 0) > now:
            return 0
        return max(0, LOGIN_MAX_ATTEMPTS - len(_failures.get(key, ())))


def reset(key: str) -> None:
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def snapshot() -> dict:
    with _lock:
        _prune(_now())
        return {"tracked": len(_failures), "locked": len(_locked_until)}


def humanize(seconds: int) -> str:
    if seconds >= 60:
        return f"{seconds // 60 + 1} 分钟"
    return f"{seconds} 秒"
