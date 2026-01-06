from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import delete, select

from app.bot.filters.is_admin import IsAdmin
from app.infra.db.session import AsyncSessionLocal
from app.domain.cats.models import Cat, CatRarity

router = Router()


class SetCatPicState(StatesGroup):
    waiting_photo = State()


RARITY_EMOJI = {
    "common": "⚪",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟠",
    "mythic": "🔴",
}


def _rarity_valid(r: str) -> bool:
    return r in {
        CatRarity.COMMON.value,
        CatRarity.RARE.value,
        CatRarity.EPIC.value,
        CatRarity.LEGENDARY.value,
        CatRarity.MYTHIC.value,
    }


@router.message(IsAdmin(), Command("listcats"))
async def listcats(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Cat).order_by(Cat.id.asc()))
        cats = res.scalars().all()

    if not cats:
        await message.answer("📭 هیچ گربه‌ای در دیتابیس نیست.")
        return

    # ✅ بدون Markdown برای جلوگیری از parse error
    lines = ["🐱 لیست گربه‌ها:", "────────────"]
    for c in cats:
        emoji = RARITY_EMOJI.get(c.rarity, "🐱")
        pic = "✅" if c.image_file_id else "❌"
        active = "✅" if c.is_active else "⛔"
        lines.append(
            f"{emoji} #{c.id} | {c.name} | {c.rarity} | 💸 {c.price_meow} | ⚙️ {c.base_meow_amount}/{c.base_meow_interval_sec}s | 🖼 {pic} | {active}"
        )

    await message.answer("\n".join(lines))


@router.message(IsAdmin(), Command("addcat"))
async def addcat(message: Message) -> None:
    parts = (message.text or "").strip().split(maxsplit=5)
    if len(parts) != 6:
        await message.answer(
            "⚠️ فرمت درست:\n"
            "/addcat <name> <rarity> <price> <amount> <interval_sec>\n\n"
            "مثال:\n"
            "/addcat Snow common 10 1 600"
        )
        return

    name = parts[1].strip()
    rarity = parts[2].strip().lower()
    if not _rarity_valid(rarity):
        await message.answer("⚠️ rarity نامعتبر است. (common/rare/epic/legendary/mythic)")
        return

    try:
        price = int(parts[3])
        amount = int(parts[4])
        interval = int(parts[5])
    except ValueError:
        await message.answer("⚠️ price/amount/interval باید عدد باشند.")
        return

    if price <= 0 or amount < 0 or interval <= 0:
        await message.answer("⚠️ مقادیر عددی معتبر نیستند.")
        return

    async with AsyncSessionLocal() as session:
        cat = Cat(
            name=name,
            rarity=rarity,
            price_meow=price,
            base_meow_amount=amount,
            base_meow_interval_sec=interval,
            base_image_path="assets/cats/placeholder.png",
            image_file_id=None,
            is_active=True,
        )
        session.add(cat)
        await session.commit()
        await session.refresh(cat)

    await message.answer(f"✅ گربه اضافه شد: #{cat.id} | {cat.name} | {cat.rarity}")


@router.message(IsAdmin(), Command("delcat"))
async def delcat(message: Message) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ فرمت درست: /delcat <cat_id>")
        return

    try:
        cat_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ cat_id باید عدد باشد.")
        return

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Cat).where(Cat.id == cat_id))
        await session.commit()

    await message.answer(f"✅ حذف شد: {cat_id}")


@router.message(IsAdmin(), Command("togglecat"))
async def togglecat(message: Message) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ فرمت درست: /togglecat <cat_id>")
        return

    try:
        cat_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ cat_id باید عدد باشد.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Cat).where(Cat.id == cat_id))
        cat = res.scalar_one_or_none()
        if not cat:
            await message.answer("❌ cat پیدا نشد.")
            return

        cat.is_active = not cat.is_active
        await session.commit()

    state = "✅ فعال شد" if cat.is_active else "⛔ غیرفعال شد"
    await message.answer(f"{state}: {cat_id}")


@router.message(IsAdmin(), Command("setcatprice"))
async def setcatprice(message: Message) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.answer("⚠️ فرمت درست: /setcatprice <cat_id> <price>")
        return

    try:
        cat_id = int(parts[1])
        price = int(parts[2])
    except ValueError:
        await message.answer("⚠️ cat_id و price باید عدد باشند.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Cat).where(Cat.id == cat_id))
        cat = res.scalar_one_or_none()
        if not cat:
            await message.answer("❌ cat پیدا نشد.")
            return
        cat.price_meow = price
        await session.commit()

    await message.answer(f"✅ قیمت آپدیت شد: {cat_id} → 💸 {price}")


@router.message(IsAdmin(), Command("setcatgen"))
async def setcatgen(message: Message) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 4:
        await message.answer("⚠️ فرمت درست: /setcatgen <cat_id> <amount> <interval_sec>")
        return

    try:
        cat_id = int(parts[1])
        amount = int(parts[2])
        interval = int(parts[3])
    except ValueError:
        await message.answer("⚠️ عددها معتبر نیستند.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Cat).where(Cat.id == cat_id))
        cat = res.scalar_one_or_none()
        if not cat:
            await message.answer("❌ cat پیدا نشد.")
            return
        cat.base_meow_amount = amount
        cat.base_meow_interval_sec = interval
        await session.commit()

    await message.answer(f"✅ تولید آپدیت شد: {cat_id} → ⚙️ {amount}/{interval}s")


@router.message(IsAdmin(), Command("setcatpic"))
async def setcatpic_start(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ فرمت درست: /setcatpic <cat_id>")
        return

    try:
        cat_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ cat_id باید عدد باشد.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Cat).where(Cat.id == cat_id))
        cat = res.scalar_one_or_none()
        if not cat:
            await message.answer("❌ cat پیدا نشد.")
            return

    await state.set_state(SetCatPicState.waiting_photo)
    await state.update_data(cat_id=cat_id)
    await message.answer(f"📸 حالا یک عکس بفرست برای گربه #{cat_id}.")


@router.message(IsAdmin(), SetCatPicState.waiting_photo)
async def setcatpic_receive(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    cat_id = data.get("cat_id")

    if not cat_id:
        await message.answer("❌ خطا: cat_id پیدا نشد.")
        await state.clear()
        return

    if not message.photo:
        await message.answer("⚠️ باید عکس بفرستی (Photo). دوباره ارسال کن.")
        return

    file_id = message.photo[-1].file_id

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Cat).where(Cat.id == cat_id))
        cat = res.scalar_one_or_none()
        if not cat:
            await message.answer("❌ cat پیدا نشد.")
            await state.clear()
            return

        cat.image_file_id = file_id
        await session.commit()

    await state.clear()
    await message.answer(f"✅ عکس ست شد برای گربه #{cat_id}.")
