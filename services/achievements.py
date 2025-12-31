from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from db.repo_users import get_or_create_user, get_user_by_tg, update_user_fields
from db import repo_achievements
from domain.achievements import ACHIEVEMENTS


@dataclass(frozen=True)
class AchResult:
    ok: bool
    message: str


def achievements_show(user_tg: int, username: Optional[str]) -> AchResult:
    user_id = get_or_create_user(user_tg, username)
    unlocked_rows = repo_achievements.list_user_achievements(user_id)
    unlocked_ids = {r["achievement_id"] for r in unlocked_rows}

    unlocked: List[Dict[str, Any]] = []
    locked: List[Dict[str, Any]] = []

    for a in ACHIEVEMENTS:
        if a["id"] in unlocked_ids:
            unlocked.append(a)
        else:
            locked.append(a)

    lines: List[str] = ["🏆 دستاوردهای شما\n"]

    if unlocked:
        lines.append("✅ باز شده:")
        for a in unlocked:
            lines.append(f"- {a['name']}: {a['description']} (+{a.get('reward',0)})")
        lines.append("")

    if locked:
        lines.append("🔒 قفل شده:")
        for a in locked:
            lines.append(f"- {a['name']}: {a['description']}")
        lines.append("")

    total_rewards = sum(int(a.get("reward", 0)) for a in unlocked)
    lines.append(f"💰 مجموع جایزه‌های دریافتی: {total_rewards}")

    return AchResult(True, "\n".join(lines))


def award_achievement(user_tg: int, username: Optional[str], achievement_id: str) -> AchResult:
    """
    زیرساخت پاداش‌دهی (فعلاً جدا از بقیه ماژول‌ها).
    جایزه را به mew_points اضافه می‌کند اگر جدید باشد.
    """
    user_id = get_or_create_user(user_tg, username)

    ach = next((a for a in ACHIEVEMENTS if a["id"] == achievement_id), None)
    if not ach:
        return AchResult(False, "❌ achievement_id نامعتبر است.")

    added = repo_achievements.add_achievement(user_id, achievement_id)
    if not added:
        return AchResult(True, "ℹ️ این دستاورد را از قبل داشتی.")

    user = get_user_by_tg(user_tg)
    if not user:
        return AchResult(False, "❌ کاربر یافت نشد.")

    reward = int(ach.get("reward", 0))
    if reward > 0:
        points = int(user.get("mew_points") or 0)
        update_user_fields(user_tg, mew_points=points + reward)

    return AchResult(True, f"🏆 دستاورد جدید: {ach['name']}\n🎁 جایزه: {reward}")
