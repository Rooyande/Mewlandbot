# handlers/cats.py
from __future__ import annotations

from aiogram import Dispatcher, types
from aiogram.types import Message

from services import cats as cats_mod


# -------------------------
# Small helpers
# -------------------------
def _parse_need_have(err_text: str) -> tuple[int | None, int | None]:
    # err_text نمونه: "need=200,have=50"
    need = None
    have = None
    try:
        parts = [p.strip() for p in err_text.split(",")]
        for p in parts:
            if p.startswith("need="):
                need = int(p.split("=", 1)[1])
            elif p.startswith("have="):
                have = int(p.split("=", 1)[1])
    except Exception:
        return (None, None)
    return (need, have)


def _fmt_cat_line(i: int, c: dict) -> str:
    rarity = str(c.get("rarity", "common"))
    emoji = cats_mod.rarity_emoji(rarity)
    name = str(c.get("name", "گربه"))
    cid = c.get("id", "?")
    hunger = int(c.get("hunger", 0))
    happy = int(c.get("happiness", 0))
    lvl = int(c.get("level", 1))
    xp = int(c.get("xp", 0))
    need = cats_mod.xp_required_for_level(lvl)
    mph = float(c.get("mph", 0.0))

    return (
        f"{i}. {emoji} <b>{name}</b> (ID: <code>{cid}</code>)\n"
        f"   🍗 گرسنگی: {hunger}/100 | 😊 خوشحالی: {happy}/100\n"
        f"   ⬆️ سطح: {lvl} (XP: {xp}/{need})\n"
        f"   💰 درآمد: {mph:.1f} میو/ساعت"
    )


async def _reply(message: Message, text: str) -> None:
    await message.reply(text, parse_mode=types.ParseMode.HTML)


# -------------------------
# Commands
# -------------------------
async def cmd_adopt(message: Message) -> None:
    # /adopt [rarity]
    tg = message.from_user.id
    username = message.from_user.username

    arg = (message.get_args() or "").strip().lower()
    rarity = arg if arg else None

    try:
        res = cats_mod.cats_service.adopt_cat(tg, username, rarity=rarity)
    except cats_mod.ValidationError:
        await _reply(message, "❌ نوع گربه نامعتبر است.\nانواع: common, rare, epic, legendary, mythic, special")
        return
    except cats_mod.NotEnoughPoints as e:
        need, have = _parse_need_have(str(e))
        if need is not None and have is not None:
            await _reply(message, f"❌ امتیاز کافی نیست!\n💰 نیاز: {need} | 💎 دارایی: {have}")
        else:
            await _reply(message, "❌ امتیاز کافی نیست!")
        return
    except Exception:
        await _reply(message, "❌ خطای داخلی در /adopt.")
        return

    r = res["rarity"]
    cat_name = f"گربهٔ {r}"
    text = (
        "🎉 <b>گربه جدید گرفتی!</b>\n\n"
        f"{cats_mod.rarity_emoji(r)} <b>{cat_name}</b>\n"
        f"🎯 عنصر: {res['element']}\n"
        f"✨ خوی: {res['trait']}\n"
        f"💰 قیمت: {res['price']} امتیاز\n"
        f"📊 ID: <code>{res['cat_id']}</code>\n"
        f"💎 باقی‌مانده: {res['new_points']} امتیاز"
    )
    await _reply(message, text)


async def cmd_cats(message: Message) -> None:
    # /cats
    tg = message.from_user.id
    username = message.from_user.username

    try:
        owner_id = cats_mod.cats_service.get_or_create_user_id(tg, username)
        data = cats_mod.cats_service.list_cats_and_tick(owner_id)
    except Exception:
        await _reply(message, "❌ خطای داخلی در /cats.")
        return

    cats = data.get("cats", []) or []
    dead_count = int(data.get("dead_count", 0))

    if not cats and dead_count == 0:
        await _reply(message, "😿 هنوز گربه‌ای نداری!\nاز /adopt استفاده کن.")
        return

    parts: list[str] = ["🐱 <b>گربه‌های تو:</b>\n"]
    for i, c in enumerate(cats, 1):
        parts.append(_fmt_cat_line(i, c))
        parts.append("")

    if dead_count:
        parts.append(f"⚰️ {dead_count} گربه به خاطر بی‌توجهی مردند!")

    text = "\n".join(parts).strip()

    # split long messages
    if len(text) > 3800:
        for i in range(0, len(text), 3800):
            await _reply(message, text[i : i + 3800])
    else:
        await _reply(message, text)


async def cmd_feed(message: Message) -> None:
    # /feed <cat_id> <amount>
    tg = message.from_user.id
    username = message.from_user.username

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await _reply(message, "❌ فرمت: <code>/feed &lt;id&gt; &lt;amount&gt;</code>")
        return

    try:
        cat_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await _reply(message, "❌ id و amount باید عدد باشند.")
        return

    try:
        owner_id = cats_mod.cats_service.get_or_create_user_id(tg, username)
        res = cats_mod.cats_service.feed_cat(tg, owner_id, cat_id, amount)
    except cats_mod.ValidationError:
        await _reply(message, "❌ مقدار باید بین ۱ تا ۱۰۰ باشد.")
        return
    except cats_mod.NotEnoughPoints as e:
        need, have = _parse_need_have(str(e))
        if need is not None and have is not None:
            await _reply(message, f"❌ امتیاز کافی نیست!\n💰 نیاز: {need} | 💎 دارایی: {have}")
        else:
            await _reply(message, "❌ امتیاز کافی نیست!")
        return
    except cats_mod.NotFound:
        await _reply(message, "❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except cats_mod.CatDead:
        await _reply(message, "😿 این گربه مرده است!")
        return
    except Exception:
        await _reply(message, "❌ خطای داخلی در /feed.")
        return

    text = (
        f"🍗 <b>{res['cat_name']} غذاشو خورد!</b>\n\n"
        f"🍚 گرسنگی: {res['old_hunger']} → {res['new_hunger']}\n"
        f"😊 خوشحالی: {res['old_happiness']} → {res['new_happiness']}\n"
        f"💰 هزینه: {res['cost']} امتیاز\n"
        f"💎 باقی‌مانده: {res['new_points']} امتیاز"
    )
    await _reply(message, text)


async def cmd_play(message: Message) -> None:
    # /play <cat_id>
    tg = message.from_user.id
    username = message.from_user.username

    args = (message.get_args() or "").split()
    if len(args) != 1:
        await _reply(message, "❌ فرمت: <code>/play &lt;id&gt;</code>")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await _reply(message, "❌ id باید عدد باشد.")
        return

    try:
        owner_id = cats_mod.cats_service.get_or_create_user_id(tg, username)
        res = cats_mod.cats_service.play_cat(owner_id, cat_id)
    except cats_mod.NotFound:
        await _reply(message, "❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except cats_mod.CatDead:
        await _reply(message, "😿 این گربه مرده است!")
        return
    except Exception:
        await _reply(message, "❌ خطای داخلی در /play.")
        return

    text = (
        f"🎮 <b>با {res['cat_name']} بازی کردی!</b>\n\n"
        f"😊 خوشحالی: {res['old_happiness']} → {res['new_happiness']}\n"
        f"🍗 گرسنگی: {res['old_hunger']} → {res['new_hunger']}\n"
        f"⭐ XP: +{res['xp_gain']} (الان: {res['new_xp']})\n"
        f"⬆️ سطح: {res['old_level']} → {res['new_level']}"
    )
    if res.get("leveled_up"):
        text += "\n\n🎉 <b>گربه‌ات لول آپ شد!</b>"
    await _reply(message, text)


async def cmd_train(message: Message) -> None:
    # /train <cat_id> <power|agility|luck>
    tg = message.from_user.id
    username = message.from_user.username

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await _reply(message, "❌ فرمت: <code>/train &lt;id&gt; &lt;power|agility|luck&gt;</code>")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await _reply(message, "❌ id باید عدد باشد.")
        return

    stat = args[1].strip().lower()

    try:
        owner_id = cats_mod.cats_service.get_or_create_user_id(tg, username)
        res = cats_mod.cats_service.train_cat(tg, owner_id, cat_id, stat)
    except cats_mod.ValidationError:
        await _reply(message, "❌ استت نامعتبر است. موارد مجاز: power, agility, luck")
        return
    except cats_mod.NotEnoughPoints as e:
        need, have = _parse_need_have(str(e))
        if need is not None and have is not None:
            await _reply(message, f"❌ امتیاز کافی نیست!\n💰 نیاز: {need} | 💎 دارایی: {have}")
        else:
            await _reply(message, "❌ امتیاز کافی نیست!")
        return
    except cats_mod.NotFound:
        await _reply(message, "❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except cats_mod.CatDead:
        await _reply(message, "😿 این گربه مرده است!")
        return
    except Exception:
        await _reply(message, "❌ خطای داخلی در /train.")
        return

    text = (
        f"🏋️ <b>{res['cat_name']} آموزش دید!</b>\n\n"
        f"📈 {res['stat']}: {res['old_value']} → {res['new_value']}\n"
        f"💰 هزینه: {res['cost']} امتیاز\n"
        f"💎 باقی‌مانده: {res['new_points']} امتیاز"
    )
    await _reply(message, text)


async def cmd_rename(message: Message) -> None:
    # /rename <cat_id> <new_name>
    tg = message.from_user.id
    username = message.from_user.username

    args = (message.get_args() or "").split(maxsplit=1)
    if len(args) != 2:
        await _reply(message, "❌ فرمت: <code>/rename &lt;id&gt; &lt;نام جدید&gt;</code>")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await _reply(message, "❌ id باید عدد باشد.")
        return

    new_name = args[1].strip()

    try:
        owner_id = cats_mod.cats_service.get_or_create_user_id(tg, username)
        res = cats_mod.cats_service.rename_cat(owner_id, cat_id, new_name)
    except cats_mod.ValidationError:
        await _reply(message, "❌ نام نامعتبر است (حداکثر ۳۲ کاراکتر).")
        return
    except cats_mod.NotFound:
        await _reply(message, "❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except cats_mod.CatDead:
        await _reply(message, "😿 این گربه مرده است!")
        return
    except Exception:
        await _reply(message, "❌ خطای داخلی در /rename.")
        return

    await _reply(message, f"✅ اسم گربه از <b>{res['old_name']}</b> به <b>{res['new_name']}</b> تغییر کرد!")


async def cmd_shop(message: Message) -> None:
    # /shop
    items = cats_mod.GEAR_ITEMS or {}
    if not items:
        await _reply(message, "🛒 فعلاً آیتمی در فروشگاه ثبت نشده.")
        return

    lines: list[str] = ["🛒 <b>فروشگاه تجهیزات گربه</b>\n"]
    for code, it in items.items():
        name = str(it.get("name", code))
        price = int(it.get("price", 0))
        min_lvl = int(it.get("min_level", 1))
        mph = float(it.get("mph_bonus", 0.0))
        p = int(it.get("power_bonus", 0))
        a = int(it.get("agility_bonus", 0))
        l = int(it.get("luck_bonus", 0))

        lines.append(
            f"• {name} (کد: <code>{code}</code>)\n"
            f"  قیمت: {price} | نیاز به لول: {min_lvl}+\n"
            f"  بونوس: +{mph} میو/ساعت | قدرت:+{p} چابکی:+{a} شانس:+{l}\n"
        )

    lines.append("برای خرید: <code>/buygear &lt;id_گربه&gt; &lt;کد_آیتم&gt;</code>")
    await _reply(message, "\n".join(lines).strip())


async def cmd_buygear(message: Message) -> None:
    # /buygear <cat_id> <gear_code>
    tg = message.from_user.id
    username = message.from_user.username

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await _reply(message, "❌ فرمت: <code>/buygear &lt;id&gt; &lt;code&gt;</code>")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await _reply(message, "❌ id باید عدد باشد.")
        return

    gear_code = args[1].strip().lower()

    try:
        owner_id = cats_mod.cats_service.get_or_create_user_id(tg, username)
        res = cats_mod.cats_service.buy_gear(tg, owner_id, cat_id, gear_code)
    except cats_mod.ValidationError as e:
        key = str(e)
        if key == "gear_invalid":
            await _reply(message, "❌ کد آیتم نامعتبر است. /shop را چک کن.")
        elif key == "level_too_low":
            await _reply(message, "❌ لول گربه برای این آیتم کافی نیست.")
        elif key == "gear_already_equipped":
            await _reply(message, "❌ این آیتم قبلاً روی گربه نصب شده است.")
        else:
            await _reply(message, "❌ درخواست نامعتبر.")
        return
    except cats_mod.NotEnoughPoints as e:
        need, have = _parse_need_have(str(e))
        if need is not None and have is not None:
            await _reply(message, f"❌ امتیاز کافی نیست!\n💰 نیاز: {need} | 💎 دارایی: {have}")
        else:
            await _reply(message, "❌ امتیاز کافی نیست!")
        return
    except cats_mod.NotFound:
        await _reply(message, "❌ گربه پیدا نشد یا مال تو نیست.")
        return
    except cats_mod.CatDead:
        await _reply(message, "😿 این گربه مرده است!")
        return
    except Exception:
        await _reply(message, "❌ خطای داخلی در /buygear.")
        return

    text = (
        f"🎉 <b>{res['gear_name']} روی {res['cat_name']} نصب شد!</b>\n\n"
        f"💰 قیمت: {res['price']} امتیاز\n"
        f"💎 باقی‌مانده: {res['new_points']} امتیاز\n"
        f"⚡ درآمد جدید: {res['new_mph']:.1f} میو/ساعت"
    )
    await _reply(message, text)


# -------------------------
# Register
# -------------------------
def register(dp: Dispatcher) -> None:
    dp.register_message_handler(cmd_adopt, commands={"adopt"})
    dp.register_message_handler(cmd_cats, commands={"cats"})
    dp.register_message_handler(cmd_feed, commands={"feed"})
    dp.register_message_handler(cmd_play, commands={"play"})
    dp.register_message_handler(cmd_train, commands={"train"})
    dp.register_message_handler(cmd_rename, commands={"rename"})
    dp.register_message_handler(cmd_shop, commands={"shop"})
    dp.register_message_handler(cmd_buygear, commands={"buygear"})
