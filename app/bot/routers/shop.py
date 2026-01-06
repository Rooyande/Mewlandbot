from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select

from app.config.settings import settings
from app.infra.db.session import AsyncSessionLocal
from app.domain.users.service import get_or_create_user
from app.domain.items.models import Item, UserItem

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


@router.message(Command("shop"))
async def shop(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Item).where(Item.is_active == True).order_by(Item.id.asc())  # noqa: E712
        )
        items = res.scalars().all()

    if not items:
        await message.answer("🛒 شاپ خالیه. هنوز آیتمی اضافه نشده.")
        return

    lines = ["🛒 شاپ آیتم‌ها", "────────────"]
    for it in items:
        pic = "✅" if it.image_file_id else "❌"
        lines.append(
            f"🧩 #{it.id} | {it.name} | 💸 {it.price_meow} | 🎯 {it.effect_type}:{it.effect_value} | 🖼 {pic}"
        )

    lines.append("────────────")
    lines.append("🛍 خرید: /buyitem <id>")
    lines.append("📦 آیتم‌های من: /myitems")

    await message.answer("\n".join(lines))


@router.message(Command("buyitem"))
async def buyitem(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return
    if not _is_allowed_group(message):
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ فرمت درست: /buyitem <item_id>")
        return

    try:
        item_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ item_id باید عدد باشد.")
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        res = await session.execute(select(Item).where(Item.id == item_id))
        item = res.scalar_one_or_none()
        if not item or not item.is_active:
            await message.answer("❌ این آیتم وجود ندارد یا غیرفعال است.")
            return

        if user.meow_points < item.price_meow:
            await message.answer(
                f"❌ موجودی کافی نیست.\n"
                f"💸 قیمت: {item.price_meow}\n"
                f"🪙 موجودی شما: {user.meow_points}"
            )
            return

        # کم کردن امتیاز
        user.meow_points -= item.price_meow

        # اگر قبلاً داشته باشد → quantity++
        res2 = await session.execute(
            select(UserItem).where(
                UserItem.user_telegram_id == user.telegram_id,
                UserItem.item_id == item.id,
            )
        )
        ui = res2.scalar_one_or_none()
        if ui:
            ui.quantity += 1
        else:
            ui = UserItem(user_telegram_id=user.telegram_id, item_id=item.id, quantity=1)
            session.add(ui)

        await session.commit()

    await message.answer(
        "✅ خرید انجام شد!\n"
        "────────────\n"
        f"🧩 آیتم: {item.name}\n"
        f"🎯 تاثیر: {item.effect_type}:{item.effect_value}\n"
        f"🪙 موجودی جدید: {user.meow_points}\n"
        "────────────\n"
        "📦 /myitems"
    )


@router.message(Command("myitems"))
async def myitems(message: Message) -> None:
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

        res = await session.execute(
            select(UserItem.item_id, func.sum(UserItem.quantity))
            .where(UserItem.user_telegram_id == user.telegram_id)
            .group_by(UserItem.item_id)
        )
        rows = res.all()

        if not rows:
            await message.answer("📦 شما هنوز هیچ آیتمی نخریدی.")
            return

        # گرفتن اطلاعات آیتم‌ها
        item_ids = [r[0] for r in rows]
        res2 = await session.execute(select(Item).where(Item.id.in_(item_ids)))
        items = {it.id: it for it in res2.scalars().all()}

    lines = ["📦 آیتم‌های شما", "────────────"]
    for item_id, qty in rows:
        it = items.get(item_id)
        if not it:
            continue
        lines.append(f"🧩 #{it.id} | {it.name} | x{qty} | 🎯 {it.effect_type}:{it.effect_value}")

    lines.append("────────────")
    lines.append("🛒 شاپ: /shop")

    await message.answer("\n".join(lines))
