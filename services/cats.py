import random
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from domain.constants import (
    RARITY_CONFIG,
    choose_rarity,
    ELEMENTS,
    TRAITS,
    rarity_emoji,
)
from db.repo_users import get_or_create_user, get_user_by_tg, update_user_fields
from db.repo_cats import add_cat, list_user_cats, get_cat, kill_cat
from services.cat_tick import apply_cat_tick, persist_tick


@dataclass(frozen=True)
class AdoptResult:
    ok: bool
    message: str


def adopt_cat(telegram_id: int, username: Optional[str], rarity_arg: Optional[str]) -> AdoptResult:
    user_db_id = get_or_create_user(telegram_id, username)
    user = get_user_by_tg(telegram_id)
    if not user:
        return AdoptResult(False, "❌ خطا در بارگذاری کاربر.")

    points = int(user.get("mew_points") or 0)

    if rarity_arg:
        rarity = rarity_arg.strip().lower()
        if rarity not in RARITY_CONFIG:
            return AdoptResult(False, "❌ نوع گربه نامعتبر است. انواع: common, rare, epic, legendary, mythic, special")
    else:
        rarity = choose_rarity()

    price = int(RARITY_CONFIG[rarity]["price"])
    if points < price:
        return AdoptResult(
            False,
            f"❌ امتیاز کافی نیست!\n💰 نیاز: {price} | 💎 دارایی: {points}\nبا تایپ mew امتیاز جمع کن.",
        )

    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    name = f"گربهٔ {rarity}"
    description = f"یک گربه‌ی {rarity} با عنصر {element} و خوی {trait}"

    cat_id = add_cat(user_db_id, name, rarity, element, trait, description)
    if not cat_id:
        return AdoptResult(False, "❌ خطا در ایجاد گربه.")

    update_user_fields(telegram_id, mew_points=points - price)

    return AdoptResult(
        True,
        "🎉 گربه جدید گرفتی!\n"
        f"{rarity_emoji(rarity)} {name}\n"
        f"🆔 ID: {cat_id}\n"
        f"🎯 عنصر: {element}\n"
        f"✨ خوی: {trait}\n"
        f"💰 قیمت: {price}\n"
        f"💎 باقی‌مانده: {points - price}",
    )


def get_my_cats_text(user_db_id: int) -> str:
    cats = list_user_cats(user_db_id, include_dead=False)
    if not cats:
        return "😿 هنوز گربه‌ای نداری. از /adopt استفاده کن."

    dead = 0
    lines: List[str] = ["🐱 گربه‌های تو:\n"]

    for i, c in enumerate(cats, 1):
        updated = apply_cat_tick(c)
        if not updated:
            kill_cat(int(c["id"]), user_db_id)
            dead += 1
            continue

        persist_tick(user_db_id, updated)

        lines.append(
            f"{i}. {rarity_emoji(updated.get('rarity','common'))} {updated.get('name')} "
            f"(ID: {updated.get('id')}) | lvl: {updated.get('level',1)}\n"
            f"   🍗 گرسنگی: {updated.get('hunger',0)}/100 | 😊 خوشحالی: {updated.get('happiness',0)}/100"
        )

    if dead:
        lines.append(f"\n⚰️ {dead} گربه به دلیل بی‌توجهی مردند.")

    return "\n".join(lines)


@dataclass(frozen=True)
class FeedResult:
    ok: bool
    message: str


def feed_cat(user_tg: int, username: Optional[str], cat_id: int, amount: int) -> FeedResult:
    user_db_id = get_or_create_user(user_tg, username)
    user = get_user_by_tg(user_tg)
    if not user:
        return FeedResult(False, "❌ کاربر یافت نشد.")

    if amount <= 0 or amount > 100:
        return FeedResult(False, "❌ مقدار باید بین ۱ تا ۱۰۰ باشد.")

    cost = amount * 2
    points = int(user.get("mew_points") or 0)
    if points < cost:
        return FeedResult(False, f"❌ امتیاز کافی نیست!\n💰 نیاز: {cost} | 💎 دارایی: {points}")

    cat = get_cat(cat_id, user_db_id)
    if not cat:
        return FeedResult(False, "❌ گربه یافت نشد یا مال تو نیست!")

    updated = apply_cat_tick(cat)
    if not updated:
        kill_cat(cat_id, user_db_id)
        return FeedResult(False, "😿 این گربه مرده است!")

    old_h = int(updated.get("hunger", 100))
    old_hp = int(updated.get("happiness", 100))

    new_h = min(100, old_h + amount)
    new_hp = min(100, old_hp + (amount // 3))

    persist_tick(user_db_id, {**updated, "hunger": new_h, "happiness": new_hp})
    update_user_fields(user_tg, mew_points=points - cost)

    return FeedResult(
        True,
        f"🍗 غذا دادی!\n"
        f"🆔 گربه: {cat_id}\n"
        f"🍚 گرسنگی: {old_h} → {new_h}\n"
        f"😊 خوشحالی: {old_hp} → {new_hp}\n"
        f"💰 هزینه: {cost}\n"
        f"💎 باقی‌مانده: {points - cost}"
    )


@dataclass(frozen=True)
class PlayResult:
    ok: bool
    message: str


def play_cat(user_tg: int, username: Optional[str], cat_id: int) -> PlayResult:
    user_db_id = get_or_create_user(user_tg, username)

    cat = get_cat(cat_id, user_db_id)
    if not cat:
        return PlayResult(False, "❌ گربه یافت نشد یا مال تو نیست!")

    updated = apply_cat_tick(cat)
    if not updated:
        kill_cat(cat_id, user_db_id)
        return PlayResult(False, "😿 این گربه مرده است!")

    old_hp = int(updated.get("happiness", 100))
    old_h = int(updated.get("hunger", 100))
    old_xp = int(updated.get("xp", 0))
    old_lvl = int(updated.get("level", 1))

    happiness_gain = 15
    hunger_loss = 5
    xp_gain = 25

    new_hp = min(100, old_hp + happiness_gain)
    new_h = max(0, old_h - hunger_loss)
    new_xp = old_xp + xp_gain
    new_lvl = old_lvl

    # level up ساده v1
    # هر لول 100xp ثابت (فعلاً)
    while new_xp >= 100:
        new_xp -= 100
        new_lvl += 1

    persist_tick(
        user_db_id,
        {
            **updated,
            "hunger": new_h,
            "happiness": new_hp,
            "xp": new_xp,
            "level": new_lvl,
        },
    )

    msg = (
        "🎮 بازی کردی!\n"
        f"🆔 گربه: {cat_id}\n"
        f"😊 خوشحالی: {old_hp} → {new_hp}\n"
        f"🍗 گرسنگی: {old_h} → {new_h}\n"
        f"⭐ XP: {old_xp} → {new_xp}\n"
        f"⬆️ لول: {old_lvl} → {new_lvl}"
    )
    return PlayResult(True, msg)
