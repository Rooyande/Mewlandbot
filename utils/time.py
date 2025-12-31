import time


def now_ts() -> int:
    return int(time.time())


def format_mm_ss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m = seconds // 60
    s = seconds % 60
    return f"{m} دقیقه و {s} ثانیه"

