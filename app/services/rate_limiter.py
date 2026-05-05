import time

_cooldowns: dict[str, float] = {}
COOLDOWN_SECONDS = 60


def can_send(email: str) -> bool:
    last_sent = _cooldowns.get(email)
    if last_sent is None:
        return True
    return (time.time() - last_sent) >= COOLDOWN_SECONDS


def record_send(email: str) -> None:
    _cooldowns[email] = time.time()


def remaining_seconds(email: str) -> int:
    last_sent = _cooldowns.get(email)
    if last_sent is None:
        return 0
    elapsed = time.time() - last_sent
    return max(0, int(COOLDOWN_SECONDS - elapsed))
