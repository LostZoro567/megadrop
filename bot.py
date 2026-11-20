import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, ChatMemberUpdated, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import broadcast as bc
from config import ADMIN_IDS, BOT_TOKEN
from content import WELCOME_BUTTONS, WELCOME_IMAGE, WELCOME_TEXT_1, WELCOME_TEXT_2
from db import DB
from features import admin_router as support_admin_router
from features import router as features_router
from features import start_keyboard

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

router = Router()
admin = Router()
admin.message.filter(F.from_user.id.in_(ADMIN_IDS))
admin.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

_tasks: set[asyncio.Task] = set()


def spawn(coro):
    """Run something in the background without blocking the reply."""
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


# ───────────────────────── /start ─────────────────────────
_image_cache = None  # Telegram file_id after first upload = instant afterwards


async def send_welcome_image(bot: Bot, chat_id: int):
    global _image_cache
    if not WELCOME_IMAGE:
        return
    src = _image_cache
    if src is None:
        if WELCOME_IMAGE.startswith(("http://", "https://")):
            src = WELCOME_IMAGE
        elif os.path.isfile(WELCOME_IMAGE):
            src = FSInputFile(WELCOME_IMAGE)
        else:
            src = WELCOME_IMAGE  # assume it's a file_id
    try:
        msg = await bot.send_photo(chat_id, src)
        if _image_cache is None and msg.photo:
            _image_cache = msg.photo[-1].file_id
    except Exception as e:
        log.error("welcome image failed: %s", e)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, db: DB, state: FSMContext):
    await state.clear()
    spawn(db.upsert_user(message.from_user))  # save user in background
    chat_id = message.chat.id
    await send_welcome_image(bot, chat_id)           # 1) image
    await message.answer(WELCOME_TEXT_1)             # 2) text
    await message.answer(                            # 3) text + buttons
        WELCOME_TEXT_2, reply_markup=start_keyboard()
    )


@router.my_chat_member()
async def on_block_unblock(event: ChatMemberUpdated, db: DB):
    if event.chat.type != "private":
        return
    status = event.new_chat_member.status
    if status == ChatMemberStatus.KICKED:
        spawn(db.set_blocked([event.chat.id], True))
    elif status == ChatMemberStatus.MEMBER:
        spawn(db.set_blocked([event.chat.id], False))


# ───────────────────── admin: /stats /broadcast ─────────────────────
class BC(StatesGroup):
    media = State()
    text = State()
    buttons = State()
    confirm = State()


def parse_buttons(raw: str):
    out = []
    for line in raw.strip().splitlines():
        if "|" not in line:
            raise ValueError(f"Missing '|' in: {line}")
        label, url = (x.strip() for x in line.split("|", 1))
        if not label or not url.startswith(("http://", "https://", "tg://")):
            raise ValueError(f"Bad button: {line}")
        out.append((label, url))
    return out


@admin.message(Command("stats"))
async def cmd_stats(message: Message, db: DB):
    total = await db.count_users()
    blocked = await db.count_users(blocked=True)
    await message.answer(
        f"👥 Total: <b>{total}</b>\n✅ Active: <b>{total - blocked}</b>\n🚫 Blocked: <b>{blocked}</b>"
    )


@admin.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Cancelled.")


@admin.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if bc.running:
        return await message.answer("⏳ A broadcast is already running. Wait for it to finish.")
    await state.clear()
    await state.set_state(BC.media)
    await message.answer(
        "📣 <b>New broadcast</b>\n\nStep 1/3: send a <b>photo or video</b> "
        "(add the text as caption if you like), or /skip for text only.\n/cancel to abort."
    )


async def ask_buttons(message: Message, state: FSMContext):
    await state.set_state(BC.buttons)
    await message.answer(
        "Step 3/3: send the <b>buttons</b>, one per line:\n"
        "<code>Button text | https://link.com</code>\n\nOr /skip for no buttons."
    )


@admin.message(BC.media, Command("skip"))
async def bc_media_skip(message: Message, state: FSMContext):
    await state.update_data(type=None, file_id=None)
    await state.set_state(BC.text)
    await message.answer("Step 2/3: send the <b>text</b> (formatting is kept).")


@admin.message(BC.media, F.photo | F.video)
async def bc_media(message: Message, state: FSMContext):
    if message.photo:
        await state.update_data(type="photo", file_id=message.photo[-1].file_id)
    else:
        await state.update_data(type="video", file_id=message.video.file_id)
    if message.caption:
        await state.update_data(text=message.html_text)
        return await ask_buttons(message, state)
    await state.set_state(BC.text)
    await message.answer("Step 2/3: send the <b>text/caption</b> (formatting is kept).")


@admin.message(BC.text, F.text)
async def bc_text(message: Message, state: FSMContext):
    data = await state.get_data()
    limit = 1024 if data.get("type") else 4096
    if len(message.text) > limit:
        return await message.answer(f"Too long ({len(message.text)}). Max {limit} characters.")
    await state.update_data(text=message.html_text)
    await ask_buttons(message, state)


async def show_preview(message: Message, state: FSMContext, bot: Bot, db: DB):
    data = await state.get_data()
    await bc.send_payload(bot, message.chat.id, data)
    n = await db.count_users(blocked=False)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Send to {n} users", callback_data="bc:go")
    kb.button(text="❌ Cancel", callback_data="bc:cancel")
    kb.adjust(1)
    await state.set_state(BC.confirm)
    await message.answer("👆 Preview. Send it?", reply_markup=kb.as_markup())


@admin.message(BC.buttons, Command("skip"))
async def bc_buttons_skip(message: Message, state: FSMContext, bot: Bot, db: DB):
    await state.update_data(buttons=[])
    await show_preview(message, state, bot, db)


@admin.message(BC.buttons, F.text)
async def bc_buttons(message: Message, state: FSMContext, bot: Bot, db: DB):
    try:
        buttons = parse_buttons(message.text)
    except ValueError as e:
        return await message.answer(f"❌ {e}\nFormat: <code>Text | https://link</code>")
    await state.update_data(buttons=buttons)
    await show_preview(message, state, bot, db)


@admin.callback_query(BC.confirm, F.data == "bc:go")
async def bc_go(call: CallbackQuery, state: FSMContext, bot: Bot, db: DB):
    if bc.running:
        return await call.answer("A broadcast is already running.", show_alert=True)
    payload = await state.get_data()
    await state.clear()
    await call.message.edit_text("🚀 Broadcast launched in the background.")
    await call.answer()
    spawn(bc.run_broadcast(bot, db, call.from_user.id, payload))


@admin.callback_query(BC.confirm, F.data == "bc:cancel")
async def bc_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Cancelled.")
    await call.answer()


# ───────────────────────── main ─────────────────────────
async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    db = DB()
    dp = Dispatcher(storage=MemoryStorage(), db=db)
    dp.include_router(admin)
    dp.include_router(router)
    dp.include_router(support_admin_router)
    dp.include_router(features_router)
    await bot.delete_webhook()
    log.info("Bot started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main())
