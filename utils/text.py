def bold(s: str) -> str:
    # فعلاً ساده (برای HTML/Markdown در آینده قابل تغییر)
    return s


def medal(i: int) -> str:
    if i == 1:
        return "🥇"
    if i == 2:
        return "🥈"
    if i == 3:
        return "🥉"
    return f"{i}."


def safe_username(username: str | None, telegram_id: int) -> str:
    u = (username or "").strip()
    if u:
        return u
    return f"کاربر {telegram_id}"

