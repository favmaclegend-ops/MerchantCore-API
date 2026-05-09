import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, maxsize: int = 1024, ttl: int = 60):
        self._maxsize = maxsize
        self._ttl = ttl
        self._data: OrderedDict[str, float] = OrderedDict()

    def _evict(self) -> None:
        now = time.time()
        while self._data:
            key, ts = next(iter(self._data.items()))
            if now - ts >= self._ttl:
                self._data.popitem(last=False)
            else:
                break

    def __contains__(self, key: str) -> bool:
        self._evict()
        return key in self._data

    def __getitem__(self, key: str) -> float:
        self._data.move_to_end(key)
        return self._data[key]

    def __setitem__(self, key: str, value: float) -> None:
        self._evict()
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def pop(self, key: str, default=None):
        return self._data.pop(key, default)

    @property
    def ttl(self) -> int:
        return self._ttl


_cooldowns = TTLCache(maxsize=1024, ttl=60)
COOLDOWN_SECONDS = 60


def can_send(email: str) -> bool:
    return email not in _cooldowns


def record_send(email: str) -> None:
    _cooldowns[email] = time.time()


def remaining_seconds(email: str) -> int:
    if email not in _cooldowns:
        return 0
    elapsed = time.time() - _cooldowns[email]
    return max(0, int(COOLDOWN_SECONDS - elapsed))
