# handlers/cats.py
from __future__ import annotations

from aiogram import Dispatcher, types
from aiogram.types import Message

from services import cats as cats_service


def _fmt_cat_line(i: int, c: dict) -> str:
    rarity = c.get("rarity", "common")
    emoji = cats_service.rarity_emoji(rarity)
    name = c.get("name", "گربه")
    cid = c.get("id", "?")
    hunger = c.get("hunger", 0)
    happy = c.get("happiness", 0)
    lvl = c.get("level", 1)
    xp = c.get("xp", 0)
    need = cats_service.xp_required_for_level(int(lvl))
    mph = float(c.get("mph", 0.0))
    return (
        f"{i}. {emoji} <b>{name}</b> (ID: <code>{cid}</code>)\n"
        f"   🍗 گرسنگی: {hunger}/100 | 😊 خوشحالی: {happy}/100\n"
        f"   ⬆️ سطح: {lvl} (XP: {xp}/{need})\n"
        f"   💰 درآمد: {mph:.1f} میو/ساعت"
    )


async def cmd_adopt(message: Message) -> None:
    # /adopt [rarity]
    tg = message.from_user.id
    username = message.from_user.username
    args = (message.get_args() or "").strip().lower()
    rarity = args if args else None

    try:
        result = cats_service.adopt_cat(tg, username, rarity=rarity)
    except cats_service.InvalidInput:
        await message.reply("❌ نوع نامعتبر است.\nانواع: common, rare, epic, legendary, mythic, special")
        return
    except cats_service.NotEnoughPoints as e:
        # تلاش برای نمایش عددها اگر در متن exception باشد
        await message.reply("❌ امتیاز کافی نیست. با mew امتیاز جمع کن.")
        return
    except Exception:
        await message.reply("❌ خطای داخلی در خرید گربه.")
        return

    text = (
        "🎉 <b>گربه جدید گرفتی!</b>\n\n"
        f"{cats_service.rarity_emoji(result['rarity'])} <b>{result['name']}</b>\n"
        f"🎯 عنصر: {result['element']}\n"
        f"✨ خوی: {result['trait']}\n"
        f"💰 قیمت: {result['price']} امتیاز\n"
        f"📊 ID: <code>{result['cat_id']}</code>\n"
        f"💎 باقی‌مانده: {result['points_after']} امتیاز"
    )
    await message.reply(text)


async def cmd_cats(message: Message) -> None:
    # /cats
    tg = message.from_user.id
    username = message.from_user.username

    # اینجا فرض می‌کنیم repo_users متصل است و می‌توانیم user_db_id را از سرویس بگیریم
    try:
        # سریع‌ترین راه: adopt/list بر اساس user_db_id
        # اگر repo_users در سرویس متصل باشد:
        user_db_id = cats_service.repo_users.get_or_create_user(tg, username)  # type: ignore
        data = cats_service.list_user_cats(user_db_id)
    except Exception:
        await message.reply("❌ خطای داخلی در دریافت لیست گربه‌ها.")
        return

    alive = data.get("alive", [])
    dead_count = int(data.get("dead_count", 0))

    if not alive and dead_count == 0:
        await message.reply("😿 هنوز گربه‌ای نداری!\nاز /adopt استفاده کن.")
        return

    parts = ["🐱 <b>گربه‌های تو:</b>\n"]
    for i, c in enumerate(alive, 1):
        parts.append(_fmt_cat_line(i, c))
        parts.append("")

    if dead_count:
        parts.append(f"⚰️ {dead_count} گربه به خاطر بی‌توجهی مردند!")

    text = "\n".join(parts).strip()

    # تقسیم پیام‌های بلند
    if len(text) > 3800:
        chunks = [text[i:i+3800] for i in range(0, len(text), 3800)]
        for ch in chunks:
            await message.reply(ch)
    else:
        await message.reply(text)


async def cmd_feed(message: Message) -> None:
    # /feed <cat_id> <amount>
    tg = message.from_user.id
    username = message.from_user.username
    args = (message.get_args() or "").split()
    if len(args) != 2:
        await message.reply("❌ فرمت: /feed <id> <amount>")
        return
    try:
        cat_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await message.reply("❌ id و amount باید عدد باشند.")
        return

    try:
        user_db_id = cats_service.repo_users.get_or_create_user(tg, username)  # type: ignore
        res = cats_service.feed_cat(user_db_id, tg, cat_id, amount)
    except cats_service.InvalidInput:
        await message.reply("❌ مقدار باید بین ۱ تا ۱۰۰ باشد.")
        return
    except cats_service.NotEnoughPoints:
        await message.reply("❌ امتیاز کافی نیست.")
        return
    except cats_service.Forbidden:
        await message.reply("😿 این گربه مرده است.")
        return
    except cats_service.NotFound:
        await message.reply("❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except Exception:
        await message.reply("❌ خطای داخلی در feed.")
        return

    text = (
        f"🍗 <b>{res.get('name','گربه')} غذاشو خورد!</b>\n\n"
        f"🍚 گرسنگی: {res['hunger_before']} → {res['hunger_after']}\n"
        f"😊 خوشحالی: {res['happiness_before']} → {res['happiness_after']}\n"
        f"💰 هزینه: {res['cost']} امتیاز\n"
        f"💎 باقی‌مانده: {res['points_after']} امتیاز"
    )
    await message.reply(text)


async def cmd_play(message: Message) -> None:
    # /play <cat_id>
    tg = message.from_user.id
    username = message.from_user.username
    args = (message.get_args() or "").split()
    if len(args) != 1:
        await message.reply("❌ فرمت: /play <id>")
        return
    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("❌ id باید عدد باشد.")
        return

    try:
        user_db_id = cats_service.repo_users.get_or_create_user(tg, username)  # type: ignore
        res = cats_service.play_with_cat(user_db_id, cat_id)
    except cats_service.NotFound:
        await message.reply("❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except cats_service.Forbidden:
        await message.reply("😿 این گربه مرده است.")
        return
    except Exception:
        await message.reply("❌ خطای داخلی در play.")
        return

    text = (
        f"🎮 <b>با {res.get('name','گربه')} بازی کردی!</b>\n\n"
        f"😊 خوشحالی: {res['happiness_before']} → {res['happiness_after']}\n"
        f"🍗 گرسنگی: {res['hunger_before']} → {res['hunger_after']}\n"
        f"⭐ XP: {res['xp_before']} → {res['xp_after']}\n"
        f"⬆️ سطح: {res['level_before']} → {res['level_after']}"
    )
    if res.get("leveled_up"):
        text += "\n\n🎉 <b>لول آپ شد!</b>"
    await message.reply(text)


async def cmd_train(message: Message) -> None:
    # /train <cat_id> <power|agility|luck>
    tg = message.from_user.id
    username = message.from_user.username
    args = (message.get_args() or "").split()
    if len(args) != 2:
        await message.reply("❌ فرمت: /train <id> <power|agility|luck>")
        return
    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("❌ id باید عدد باشد.")
        return

    stat = args[1].lower().strip()

    try:
        user_db_id = cats_service.repo_users.get_or_create_user(tg, username)  # type: ignore
        res = cats_service.train_cat(user_db_id, tg, cat_id, stat)
    except cats_service.InvalidInput:
        await message.reply("❌ استت نامعتبر است. موارد مجاز: power, agility, luck")
        return
    except cats_service.NotEnoughPoints:
        await message.reply("❌ امتیاز کافی نیست.")
        return
    except cats_service.NotFound:
        await message.reply("❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except cats_service.Forbidden:
        await message.reply("😿 این گربه مرده است.")
        return
    except Exception:
        await message.reply("❌ خطای داخلی در train.")
        return

    text = (
        f"🏋️ <b>{res.get('name','گربه')} آموزش دید!</b>\n\n"
        f"📈 {res['stat']}: {res['before']} → {res['after']}\n"
        f"💰 هزینه: {res['cost']} امتیاز\n"
        f"💎 باقی‌مانده: {res['points_after']} امتیاز"
    )
    await message.reply(text)


def register(dp: Dispatcher) -> None:
    dp.register_message_handler(cmd_adopt, commands={"adopt"})
    dp.register_message_handler(cmd_cats, commands={"cats"})
    dp.register_message_handler(cmd_feed, commands={"feed"})
    dp.register_message_handler(cmd_play, commands={"play"})
    dp.register_message_handler(cmd_train, commands={"train"})
