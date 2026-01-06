from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile
from sqlalchemy import select

from app.config.settings import settings
from app.infra.db.session import AsyncSessionLocal
from app.domain.users.service import get_or_create_user
from app.domain.cats.models import Cat, UserCat
from app.domain.cats.gacha import RarityRates, pick_rarity, pick_cat_from_pool
from app.domain.cats.renderer import render_cat_image

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


RARITY_EMOJI = {
    "common": "⚪",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟠",
    "mythic": "🔴",
}


@router.message(Command("buycat"))
async def buycat(message: Message) -> None:
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

        res = await session.execute(select(Cat).where(Cat.is_active == True))  # noqa: E712
        cats = list(res.scalars().all())
        if not cats:
            await message.answer("❌ هیچ گربه‌ای برای خرید موجود نیست.")
            return

        rates = RarityRates()
        rarity = pick_rarity(rates)

        chosen = pick_cat_from_pool(cats, rarity)
        if chosen is None:
            for r in ["common", "rare", "epic", "legendary", "mythic"]:
                chosen = pick_cat_from_pool(cats, r)
                if chosen:
                    rarity = r
                    break

        if chosen is None:
            await message.answer("❌ هیچ گربه فعالی پیدا نشد.")
            return

        cost = chosen.price_meow
        if user.meow_points < cost:
            await message.answer(
                f"💸 امتیاز کافی نداری!\n"
                f"🪙 نیاز: **{cost}**\n"
                f"🪙 داری: **{user.meow_points}**",
                parse_mode="Markdown",
            )
            return

        user.meow_points -= cost

        uc = UserCat(
            user_telegram_id=user.telegram_id,
            cat_id=chosen.id,
            nickname=None,
            level=1,
            happiness=100,
            hunger=0,
            is_alive=True,
            is_left=False,
        )
        session.add(uc)
        await session.commit()
        await session.refresh(uc)

    emoji = RARITY_EMOJI.get(rarity, "🐱")

    caption = (
        f"🎉 مبارک!\n"
        f"{emoji} یک گربه **{chosen.name}** گرفتی!\n"
        f"⭐ rarity: **{rarity}**\n"
        f"💸 هزینه: **{cost}**\n"
        f"🪙 امتیاز باقی‌مانده: **{user.meow_points}**\n\n"
        f"📌 برای دیدن گربه‌هات: /mycats\n"
        f"🔎 جزئیات این گربه: /cat {uc.id}\n"
        f"🏷 اسم گذاشتن: `/namecat {uc.id} <اسم>`"
    )

    # اگر image_file_id داشت، مستقیم از تلگرام ارسال می‌کنیم
    if chosen.image_file_id:
        await message.answer_photo(photo=chosen.image_file_id, caption=caption, parse_mode="Markdown")
        return

    # اگر نداشت، fallback به placeholder/asset path
    img_path = render_cat_image(chosen.base_image_path, title=chosen.name)
    photo = FSInputFile(str(img_path))
    await message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")


@router.message(Command("mycats"))
async def mycats(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    async with AsyncSessionLocal() as session:
        await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        res = await session.execute(
            select(UserCat, Cat)
            .join(Cat, Cat.id == UserCat.cat_id)
            .where(UserCat.user_telegram_id == message.from_user.id)
            .order_by(UserCat.id.desc())
            .limit(20)
        )
        rows = res.all()

    if not rows:
        await message.answer("📭 هنوز هیچ گربه‌ای نداری.\nبرای خرید: /buycat")
        return

    lines = ["🐾 گربه‌های شما (آخرین 20 تا):", "────────────"]
    for uc, cat in rows:
        emoji = RARITY_EMOJI.get(cat.rarity, "🐱")
        nick = f" ({uc.nickname})" if uc.nickname else ""
        lines.append(f"{emoji} `#{uc.id}` **{cat.name}**{nick}  | lvl {uc.level}")

    lines.append("────────────")
    lines.append("🔎 جزئیات: `/cat <id>`")
    lines.append("🏷 اسم‌گذاری: `/namecat <id> <اسم>`")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("cat"))
async def cat_detail(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ فرمت درست: `/cat <id>`", parse_mode="Markdown")
        return

    try:
        uc_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ id باید عدد باشد.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(UserCat, Cat)
            .join(Cat, Cat.id == UserCat.cat_id)
            .where(UserCat.id == uc_id)
            .where(UserCat.user_telegram_id == message.from_user.id)
        )
        row = res.first()

    if not row:
        await message.answer("❌ این گربه برای شما نیست یا وجود ندارد.")
        return

    uc, cat = row
    emoji = RARITY_EMOJI.get(cat.rarity, "🐱")
    nick = uc.nickname or "ندارد"

    await message.answer(
        "🐱 جزئیات گربه\n"
        "────────────\n"
        f"{emoji} نام: **{cat.name}**\n"
        f"⭐ rarity: **{cat.rarity}**\n"
        f"🏷 نام دلخواه: **{nick}**\n"
        f"📈 level: **{uc.level}**\n"
        f"😊 happiness: **{uc.happiness}**\n"
        f"🍗 hunger: **{uc.hunger}**\n"
        f"❤️ alive: **{uc.is_alive}**\n"
        "────────────\n"
        f"🏷 تغییر اسم: `/namecat {uc.id} <اسم>`",
        parse_mode="Markdown",
    )


@router.message(Command("namecat"))
async def namecat(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    parts = (message.text or "").strip().split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "⚠️ فرمت درست:\n"
            "`/namecat <cat_id> <اسم>`\n"
            "مثال: `/namecat 12 MrFluffy`",
            parse_mode="Markdown",
        )
        return

    try:
        uc_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ cat_id باید عدد باشد.")
        return

    nickname = parts[2].strip()
    if len(nickname) < 1 or len(nickname) > 24:
        await message.answer("⚠️ اسم باید بین 1 تا 24 کاراکتر باشد.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(UserCat).where(UserCat.id == uc_id).where(UserCat.user_telegram_id == message.from_user.id)
        )
        uc = res.scalar_one_or_none()

        if not uc:
            await message.answer("❌ این گربه برای شما نیست یا وجود ندارد.")
            return

        uc.nickname = nickname
        await session.commit()

    await message.answer(
        f"✅ اسم گربه با موفقیت تغییر کرد.\n"
        f"🐾 `#{uc_id}` → **{nickname}**",
        parse_mode="Markdown",
    )
