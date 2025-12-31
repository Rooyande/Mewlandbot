# services/market.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from db.repo_users import get_or_create_user, get_user_by_db_id
from db.repo_cats import get_cat
from db import repo_market
from domain.constants import rarity_emoji

from services.achievements import award_achievement


@dataclass(frozen=True)
class MarketResult:
    ok: bool
    message: str


def market_list(user_tg: int, username: Optional[str], cat_id: int, price: int) -> MarketResult:
    user_id = get_or_create_user(user_tg, username)
    if price <= 0:
        return MarketResult(False, "❌ قیمت باید مثبت باشد.")

    listing_id = repo_market.create_listing(user_id, cat_id, price)
    if not listing_id:
        return MarketResult(False, "❌ نتوانستم آگهی را ایجاد کنم (مالکیت/زنده بودن/تکراری بودن را چک کن).")

    fee = int(price * repo_market.MARKET_FEE_PERCENT / 100)
    net = price - fee
    return MarketResult(
        True,
        "🏪 آگهی ثبت شد.\n"
        f"📄 ID آگهی: {listing_id}\n"
        f"🐱 ID گربه: {cat_id}\n"
        f"💰 قیمت: {price}\n"
        f"📉 کارمزد: {fee}\n"
        f"💵 خالص: {net}",
    )


def market_browse() -> str:
    listings = repo_market.list_active()
    if not listings:
        return "🏪 فعلاً آگهی فعالی وجود ندارد."

    parts: List[str] = ["🏪 بازار - آگهی‌های فعال:\n"]
    for l in listings:
        l_id = int(l["id"])
        cat_id = int(l["cat_id"])
        price = int(l["price"])
        created_at = int(l.get("created_at") or 0)
        seller_id = int(l["seller_id"])

        cat = get_cat(cat_id)
        seller = get_user_by_db_id(seller_id)

        cat_name = (cat.get("name") if cat else "گربه ناشناخته")
        rarity = (cat.get("rarity") if cat else "common")
        emoji = rarity_emoji(rarity)

        seller_name = (seller.get("username") if seller and seller.get("username") else f"User {seller_id}")

        fee = int(price * repo_market.MARKET_FEE_PERCENT / 100)
        net = price - fee

        date_str = ""
        if created_at:
            try:
                date_str = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d")
            except Exception:
                date_str = ""

        parts.append(
            f"📄 {l_id} | 🐱 {emoji} {cat_name} (cat:{cat_id}) | 💰 {price} (خالص:{net}) | 👤 {seller_name}"
            + (f" | 📅 {date_str}" if date_str else "")
        )

    parts.append("\nخرید: /market buy <listing_id>")
    return "\n".join(parts)


def market_my(user_tg: int, username: Optional[str]) -> str:
    user_id = get_or_create_user(user_tg, username)
    listings = repo_market.list_mine(user_id)
    if not listings:
        return "📦 آگهی فعالی نداری."

    parts: List[str] = ["📦 آگهی‌های تو:\n"]
    for l in listings:
        l_id = int(l["id"])
        cat_id = int(l["cat_id"])
        price = int(l["price"])
        cat = get_cat(cat_id)
        cat_name = (cat.get("name") if cat else "گربه ناشناخته")
        rarity = (cat.get("rarity") if cat else "common")
        emoji = rarity_emoji(rarity)

        fee = int(price * repo_market.MARKET_FEE_PERCENT / 100)
        net = price - fee

        parts.append(f"📄 {l_id} | 🐱 {emoji} {cat_name} (cat:{cat_id}) | 💰 {price} (خالص:{net})")

    parts.append("\nلغو: /market cancel <listing_id>")
    return "\n".join(parts)


def market_cancel(user_tg: int, username: Optional[str], listing_id: int) -> MarketResult:
    user_id = get_or_create_user(user_tg, username)
    ok = repo_market.cancel_listing(listing_id, user_id)
    if not ok:
        return MarketResult(False, "❌ نتوانستم لغو کنم (ممکن است مال تو نباشد یا منقضی شده باشد).")
    return MarketResult(True, f"✅ آگهی {listing_id} لغو شد.")


def market_buy(user_tg: int, username: Optional[str], listing_id: int) -> MarketResult:
    buyer_id = get_or_create_user(user_tg, username)
    result = repo_market.buy_listing(listing_id, buyer_id)
    if not result:
        return MarketResult(False, "❌ خرید ناموفق (آگهی/موجودی/منقضی/خرید از خودت).")

    cat_id = int(result["cat_id"])
    cat = get_cat(cat_id, buyer_id) or get_cat(cat_id)
    cat_name = (cat.get("name") if cat else f"گربه {cat_id}")

    # Achievement: market_king (برای SELLER، چون «اولین فروش موفق» است)
    ach_msg = ""
    try:
        seller_db_id = int(result["seller_id"])
        # award_achievement ورودی user_tg می‌خواهد؛ ما TG نداریم، پس از این مسیر استفاده نمی‌کنیم.
        # راه درست: یک تابع award_by_db_id بسازیم. اما در مرحله ۱۲ بدون تغییر زیاد،
        # یک راه امن: از repo_users اطلاعات seller را بگیریم و با telegram_id جایزه بدهیم.
        from db.repo_users import get_user_by_db_id  # import local to avoid cycles
        seller = get_user_by_db_id(seller_db_id)
        if seller:
            seller_tg = int(seller.get("telegram_id") or 0)
            seller_un = seller.get("username")
            if seller_tg:
                ach_res = award_achievement(seller_tg, seller_un, "market_king")
                if "دستاورد جدید" in ach_res.message:
                    ach_msg = "\n\n" + ach_res.message
    except Exception:
        ach_msg = ""

    return MarketResult(
        True,
        "🎉 خرید موفق!\n"
        f"📄 آگهی: {listing_id}\n"
        f"🐱 {cat_name} (ID:{cat_id})\n"
        f"💰 پرداختی: {result['price']}\n"
        f"📉 کارمزد: {result['fee']}\n"
        "گربه الان مال توست."
        + ach_msg
    )
