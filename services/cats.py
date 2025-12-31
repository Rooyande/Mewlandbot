import random
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from domain.constants import (
    RARITY_CONFIG,
    choose_rarity,
    ELEMENTS,
    TRAITS,
)
from db.repo_users import get_or_create_user, get_user_by_tg, update_user_fields
from db.repo_cats import add_cat, list_user_cats


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

    lines: List[str] = ["🐱 گربه‌های تو:\n"]
    for i, c in enumerate(cats, 1):
        lines.append(
            f"{i}. {c.get('name')} (ID: {c.get('id')}) | rarity: {c.get('rarity')} | lvl: {c.get('level', 1)}"
        )
    return "\n".join(lines)

