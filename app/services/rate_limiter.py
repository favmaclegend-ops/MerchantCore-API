"""Per-email verification-code rate limiting with escalating cooldowns.

Cooldown grows exponentially after every successful send (60s, 120s, 240s, ...)
and is capped at one hour. Requesting too many codes within the window
(``MAX_SENDS_BEFORE_BLOCK``) temporarily blocks the email for one hour.

State is in-memory, so it resets when the server restarts.
"""

import time
from collections import OrderedDict

WINDOW_SECONDS = 3600
COOLDOWN_SECONDS = 60
MAX_COOLDOWN_SECONDS = 3600
MAX_SENDS_BEFORE_BLOCK = 6
BLOCK_DURATION_SECONDS = 3600
_MAX_EMAILS = 1024

_cooldowns: "OrderedDict[str, float]" = OrderedDict()
_send_counts: "OrderedDict[str, int]" = OrderedDict()
_blocked_until: "OrderedDict[str, float]" = OrderedDict()


def _remember(store: OrderedDict, email: str, value) -> None:
    store[email] = value
    store.move_to_end(email)
    while len(store) > _MAX_EMAILS:
        store.popitem(last=False)


def _prune(email: str, now: float) -> None:
    last = _cooldowns.get(email)
    if last and now - last > WINDOW_SECONDS:
        _cooldowns.pop(email, None)
        _send_counts.pop(email, None)


def _backoff(sends: int) -> int:
    if sends <= 0:
        return 0
    return min(COOLDOWN_SECONDS * (2 ** (sends - 1)), MAX_COOLDOWN_SECONDS)


def _is_blocked(email: str, now: float) -> bool:
    until = _blocked_until.get(email)
    if until is None:
        return False
    if now >= until:
        _blocked_until.pop(email, None)
        _send_counts.pop(email, None)
        _cooldowns.pop(email, None)
        return False
    return True


def blocked_seconds(email: str) -> int:
    now = time.time()
    _prune(email, now)
    until = _blocked_until.get(email)
    if until is None:
        return 0
    if now >= until:
        _blocked_until.pop(email, None)
        _send_counts.pop(email, None)
        _cooldowns.pop(email, None)
        return 0
    return max(1, int(until - now))


def can_send(email: str) -> bool:
    now = time.time()
    _prune(email, now)
    if _is_blocked(email, now):
        return False
    sends = _send_counts.get(email, 0)
    if sends >= MAX_SENDS_BEFORE_BLOCK:
        return False
    last = _cooldowns.get(email)
    if last is None:
        return True
    return now - last >= _backoff(sends)


def remaining_seconds(email: str) -> int:
    now = time.time()
    _prune(email, now)
    if _is_blocked(email, now):
        return max(1, int(_blocked_until[email] - now))
    sends = _send_counts.get(email, 0)
    last = _cooldowns.get(email)
    if last is None:
        return 0
    return max(0, int(_backoff(sends) - (now - last)))


def record_send(email: str) -> None:
    now = time.time()
    _prune(email, now)
    sends = _send_counts.get(email, 0) + 1
    _remember(_send_counts, email, sends)
    _remember(_cooldowns, email, now)
    if sends >= MAX_SENDS_BEFORE_BLOCK:
        _remember(_blocked_until, email, now + BLOCK_DURATION_SECONDS)