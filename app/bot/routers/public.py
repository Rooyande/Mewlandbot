from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select

from app.config.settings import settings
from app.infra.db.session import AsyncSessionLocal
from app.domain.users.service import get_or_create_user
from app.domain.cats.models import UserCat, Cat
from app.domain.economy.offline_income import apply_offline_income

router = Router()


def _is_private_and_not_admin(message: Message) -> bool:
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and message.from_user.id != settings.admin_telegram_id
    )


def _is_allowed_group(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return True

    allowed = settings.allowed_chat_id_set()
    if not allowed:
        return True
    return message.chat.id in allowed


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s and not h:
        parts.append(f"{s}s")
    return " ".join(parts)


@router.message(Command("start"))
async def start(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    await message.answer(
        "👋 سلام!\n"
        "🐾 به دنیای Meow خوش اومدی.\n\n"
        "📌 دستورها:\n"
        "• /profile → پروفایل\n"
        "• /claim → دریافت درآمد آفلاین\n"
        "• /buycat → خرید گربه\n"
        "• /mycats → گربه‌های من\n"
        "• /help → راهنما"
    )


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    await message.answer(
        "📚 راهنما\n"
        "────────────\n"
        "👤 /profile → پروفایل و آمار\n"
        "💤 /claim → دریافت درآمد آفلاین\n"
        "🐱 /buycat → خرید گربه با امتیاز\n"
        "📋 /mycats → لیست گربه‌ها\n"
        "🔎 /cat <id> → جزئیات یک گربه\n"
        "🏷 /namecat <id> <name> → اسم گذاشتن روی گربه\n"
    )


@router.message(Command("claim"))
async def claim(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        result = await apply_offline_income(session, user)

    if result.seconds_used == 0:
        await message.answer(
            "💤 درآمد آفلاین فعلاً چیزی نداره!\n"
            "⏳ کمی صبر کن یا گربه‌های بیشتری بگیر 😺"
        )
        return

    await message.answer(
        "✅ درآمد آفلاین دریافت شد!\n"
        "────────────\n"
        f"⏱ مدت آفلاین محاسبه‌شده: {_format_duration(result.seconds_used)}\n"
        f"⚙️ نرخ تولید: {result.rate_per_sec * 60:.2f} / دقیقه\n"
        f"🪙 درآمد دریافت‌شده: +{result.earned} meow\n"
        "────────────\n"
        "📌 برای دیدن پروفایل: /profile"
    )


@router.message(Command("profile"))
async def profile(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        # ✅ Claim اتوماتیک قبل از نمایش پروفایل
        claim_result = await apply_offline_income(session, user)

        # ✅ تعداد گربه‌های کاربر
        cats_count_res = await session.execute(
            select(func.count())
            .select_from(UserCat)
            .where(UserCat.user_telegram_id == user.telegram_id)
        )
        cats_count = int(cats_count_res.scalar() or 0)

        # ✅ نرخ تولید (بر اساس گربه‌ها)
        gen_res = await session.execute(
            select(Cat.base_meow_amount, Cat.base_meow_interval_sec)
            .join(UserCat, UserCat.cat_id == Cat.id)
            .where(UserCat.user_telegram_id == user.telegram_id)
            .where(UserCat.is_alive == True)  # noqa: E712
            .where(UserCat.is_left == False)  # noqa: E712
        )
        rows = gen_res.all()

    total_per_sec = 0.0
    for amount, interval_sec in rows:
        if interval_sec and interval_sec > 0:
            total_per_sec += float(amount) / float(interval_sec)

    per_min = total_per_sec * 60
    per_hour = total_per_sec * 3600

    username = message.from_user.username or "—"

    claim_line = ""
    if claim_result.earned > 0:
        claim_line = (
            "\n"
            "💤 درآمد آفلاین همین الان دریافت شد!\n"
            f"🪙 +{claim_result.earned} meow (از {_format_duration(claim_result.seconds_used)})\n"
        )

    await message.answer(
        "👤 پروفایل شما\n"
        "────────────\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"👤 Username: @{username}\n\n"
        f"🪙 Meow Points: {user.meow_points}\n"
        f"🐾 تعداد گربه‌ها: {cats_count}\n\n"
        "⚙️ تولید آفلاین (از گربه‌ها)\n"
        f"⏱ {per_min:.2f} meow / دقیقه\n"
        f"🕐 {per_hour:.2f} meow / ساعت\n"
        f"{claim_line}"
        "────────────\n"
        "🐱 خرید گربه: /buycat\n"
        "📋 گربه‌ها: /mycats\n"
        "💤 دریافت دستی آفلاین: /claim"
    )
