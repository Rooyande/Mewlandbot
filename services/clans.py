# services/clans.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from db.repo_users import get_or_create_user, get_user_by_tg, update_user_fields
from db import repo_clans
from services.achievements import award_achievement


@dataclass(frozen=True)
class ClanResult:
    ok: bool
    message: str


def clan_help_text() -> str:
    return (
        "👥 کلن\n\n"
        "دستورات:\n"
        "/clan create <name> (هزینه 5000)\n"
        "/clan join <name>\n"
        "/clan leave\n"
        "/clan members\n"
        "/clan list\n"
        "/clan info <name>\n"
        "/clan bonus\n"
    )


def clan_create(user_tg: int, username: Optional[str], name: str) -> ClanResult:
    user_id = get_or_create_user(user_tg, username)
    user = get_user_by_tg(user_tg)
    if not user:
        return ClanResult(False, "❌ کاربر یافت نشد.")

    name = (name or "").strip()
    if len(name) < 3 or len(name) > 32:
        return ClanResult(False, "❌ نام کلن باید بین ۳ تا ۳۲ کاراکتر باشد.")

    points = int(user.get("mew_points") or 0)
    cost = int(repo_clans.CLAN_CREATION_COST)
    if points < cost:
        return ClanResult(False, f"❌ امتیاز کافی نیست! نیاز: {cost} | داری: {points}")

    ok = repo_clans.create_clan(user_id, name)
    if not ok:
        return ClanResult(False, "❌ ایجاد کلن ناموفق (نام تکراری یا شما قبلاً عضو کلن هستید).")

    update_user_fields(user_tg, mew_points=points - cost)

    # ---- Achievements (clan_leader) ----
    try:
        award_achievement(user_tg, username, "clan_leader")
    except Exception:
        pass

    return ClanResult(True, f"🎉 کلن {name} ساخته شد.\n💰 هزینه: {cost}")


def clan_join(user_tg: int, username: Optional[str], name: str) -> ClanResult:
    user_id = get_or_create_user(user_tg, username)
    clan_name = (name or "").strip()
    ok = repo_clans.join_clan(user_id, clan_name)
    if not ok:
        return ClanResult(False, "❌ عضویت ناموفق (کلن وجود ندارد/پر است/شما قبلاً عضو کلن هستید).")
    return ClanResult(True, f"✅ به کلن {clan_name} پیوستی.")


def clan_leave(user_tg: int, username: Optional[str]) -> ClanResult:
    user_id = get_or_create_user(user_tg, username)
    info = repo_clans.leave_clan(user_id)
    if not info:
        return ClanResult(False, "❌ شما عضو هیچ کلنی نیستید.")

    if info["was_leader"]:
        repo_clans.delete_clan(int(info["clan_id"]))
        return ClanResult(True, f"🗑️ کلن {info['clan_name']} منحل شد (رهبر خارج شد).")

    return ClanResult(True, f"👋 از کلن {info['clan_name']} خارج شدی.")


def clan_members(user_tg: int, username: Optional[str]) -> ClanResult:
    user_id = get_or_create_user(user_tg, username)
    clan = repo_clans.get_user_clan(user_id)
    if not clan:
        return ClanResult(False, "❌ شما عضو هیچ کلنی نیستید.")

    members = repo_clans.get_members(int(clan["id"]))
    lines: List[str] = [f"👥 اعضای کلن {clan['name']}:\n"]
    for i, m in enumerate(members, 1):
        role = "👑" if int(m["user_id"]) == int(clan["leader_id"]) else "👤"
        uname = m.get("username") or f"User {m.get('telegram_id')}"
        lines.append(f"{i}. {role} {uname} - {int(m.get('mew_points') or 0)}")

    return ClanResult(True, "\n".join(lines))


def clan_list() -> ClanResult:
    clans = repo_clans.list_available()
    if not clans:
        return ClanResult(True, "🏛️ فعلاً کلنی برای پیوستن وجود ندارد.")

    lines: List[str] = ["🏛️ کلن‌های موجود:\n"]
    for i, c in enumerate(clans, 1):
        members = repo_clans.get_members(int(c["id"]))
        bonus = repo_clans.calc_bonus(len(members))
        leader = c.get("leader_username") or "نامشخص"
        lines.append(
            f"{i}. {c['name']} | اعضا:{len(members)}/{repo_clans.CLAN_MAX_MEMBERS} | رهبر:{leader} | بونوس:+{int((bonus-1)*100)}%"
        )

    lines.append("\nپیوستن: /clan join <name>")
    return ClanResult(True, "\n".join(lines))


def clan_info_by_name(name: str) -> ClanResult:
    clan = repo_clans.get_clan_by_name((name or "").strip())
    if not clan:
        return ClanResult(False, "❌ کلن یافت نشد.")

    members = repo_clans.get_members(int(clan["id"]))
    bonus = repo_clans.calc_bonus(len(members))

    created_at = int(clan.get("created_at") or 0)
    created_str = ""
    if created_at:
        try:
            created_str = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d")
        except Exception:
            created_str = ""

    lines: List[str] = [
        f"🏛️ اطلاعات کلن {clan['name']}\n",
        f"👑 رهبر: {clan.get('leader_username') or 'نامشخص'}",
        f"👥 اعضا: {len(members)}/{repo_clans.CLAN_MAX_MEMBERS}",
        f"🎯 بونوس: +{int((bonus-1)*100)}%",
    ]
    if created_str:
        lines.append(f"📅 ایجاد: {created_str}")

    lines.append("\nبرترین‌ها:")
    for i, m in enumerate(members[:3], 1):
        uname = m.get("username") or "کاربر"
        lines.append(f"{i}. {uname} - {int(m.get('mew_points') or 0)}")

    lines.append(f"\nپیوستن: /clan join {clan['name']}")
    return ClanResult(True, "\n".join(lines))


def clan_bonus(user_tg: int, username: Optional[str]) -> ClanResult:
    user_id = get_or_create_user(user_tg, username)
    clan = repo_clans.get_user_clan(user_id)
    if not clan:
        return ClanResult(False, "❌ شما عضو هیچ کلنی نیستید.")

    members = repo_clans.get_members(int(clan["id"]))
    bonus = repo_clans.calc_bonus(len(members))

    return ClanResult(
        True,
        f"🎯 بونوس کلن {clan['name']}\n"
        f"👥 اعضا: {len(members)}\n"
        f"📊 بونوس فعلی: +{int((bonus-1)*100)}%\n"
        f"💰 به ازای هر عضو: +{int(repo_clans.CLAN_BONUS_PER_MEMBER*100)}%",
    )
