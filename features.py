"""Preview (language -> images -> link) and 24x7 Support (user <-> admin)."""
import asyncio
import logging
import os
import re
import time
from collections import OrderedDict
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import content as C
from config import ADMIN_IDS

log = logging.getLogger("features")
router = Router()          # user-facing handlers
admin_router = Router()    # admin replies
admin_router.message.filter(F.from_user.id.in_(ADMIN_IDS))

_tasks: set[asyncio.Task] = set()


def spawn(coro):
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


# ───────────────── /start keyboard ─────────────────
def start_keyboard() -> InlineKeyboardMarkup:
    """Row 1: Preview | Support.  Below: all the link buttons together."""
    b = InlineKeyboardBuilder()
    b.button(text=C.PREVIEW_BTN, callback_data="preview")
    b.button(text=C.SUPPORT_BTN, callback_data="support")
    for label, url in C.WELCOME_BUTTONS:
        b.button(text=label, url=url)
    b.adjust(1)   # every button on its own row
    return b.as_markup()


# ───────────────── Preview flow ─────────────────
BUTTON_ON_EVERY_IMAGE = True   # False = button only under the last image

_cache: dict[str, str] = {}  # image path/url -> Telegram file_id (instant after 1st send)


async def send_preview_images(bot: Bot, chat_id: int, kb: InlineKeyboardMarkup):
    """Send the images one by one (no album), each with the button."""
    images = C.PREVIEW_IMAGES
    for i, path in enumerate(images):
        src = _cache.get(path)
        if src is None:
            if path.startswith(("http://", "https://")):
                src = path
            elif os.path.isfile(path):
                src = FSInputFile(path)
            else:
                log.warning("preview image missing: %s", path)
                continue
        markup = kb if (BUTTON_ON_EVERY_IMAGE or i == len(images) - 1) else None
        try:
            m = await bot.send_photo(chat_id, src, reply_markup=markup)
            if path not in _cache and m.photo:
                _cache[path] = m.photo[-1].file_id
        except Exception as e:
            log.error("preview image %s failed: %s", path, e)


@router.callback_query(F.data == "preview")
async def on_preview(call: CallbackQuery, bot: Bot):
    await call.answer()
    b = InlineKeyboardBuilder()
    for code, lang in C.LANGUAGES.items():
        b.button(text=lang["name"], callback_data=f"lang:{code}")
    b.adjust(2)
    await bot.send_message(call.from_user.id, C.CHOOSE_LANG_TEXT, reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("lang:"))
async def on_language(call: CallbackQuery, bot: Bot):
    await call.answer()
    code = call.data.split(":", 1)[1]
    lang = C.LANGUAGES.get(code) or next(iter(C.LANGUAGES.values()))
    chat_id = call.from_user.id
    b = InlineKeyboardBuilder()
    b.button(text=lang["button"], url=C.PREVIEW_LINK)
    await bot.send_message(chat_id, lang["text"])                 # intro text
    await send_preview_images(bot, chat_id, b.as_markup())        # images one by one


# ───────────────── Support: user -> admin ─────────────────
class Support(StatesGroup):
    active = State()


_map: OrderedDict[tuple[int, int], int] = OrderedDict()  # (admin_chat, msg_id) -> user_id
_last_header: dict[int, float] = {}
HEADER_GAP = 120  # seconds: new user-info header at most every 2 min per user
_ID_RE = re.compile(r"🆔\s*(\d{5,})")


def _remember(admin_id: int, msg_id: int, user_id: int):
    _map[(admin_id, msg_id)] = user_id
    while len(_map) > 5000:
        _map.popitem(last=False)


@router.callback_query(F.data == "support")
async def on_support(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    await state.set_state(Support.active)
    await bot.send_message(call.from_user.id, C.SUPPORT_TEXT)


@router.message(Support.active, Command("cancel"))
async def support_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Support closed. Send /start anytime to begin again.")


async def forward_to_admins(bot: Bot, message: Message):
    u = message.from_user
    uname = f"@{escape(u.username)}" if u.username else "no username"
    header = (
        f"💬 <b>Support message</b>\n"
        f"👤 {escape(u.full_name)} ({uname})\n"
        f"🆔 <code>{u.id}</code>\n\n"
        f"↩️ Reply to this message or the one below to answer the user."
    )
    now = time.monotonic()
    send_header = now - _last_header.get(u.id, 0) > HEADER_GAP
    if send_header:
        if len(_last_header) > 10000:
            _last_header.clear()
        _last_header[u.id] = now
    for admin_id in ADMIN_IDS:
        try:
            if send_header:
                h = await bot.send_message(admin_id, header)
                _remember(admin_id, h.message_id, u.id)
            c = await bot.copy_message(admin_id, message.chat.id, message.message_id)
            _remember(admin_id, c.message_id, u.id)
        except TelegramAPIError as e:
            log.error("forward to admin %s failed: %s", admin_id, e)


async def _ack(bot: Bot, message: Message, fallback: str):
    try:
        await bot.set_message_reaction(
            message.chat.id, message.message_id, [ReactionTypeEmoji(emoji="👍")]
        )
    except Exception:
        await message.answer(fallback)


@router.message(Support.active)
async def on_support_message(message: Message, bot: Bot):
    if not ADMIN_IDS:
        return await message.answer("Support is unavailable right now.")
    spawn(forward_to_admins(bot, message))   # text, links, photo, video, files...
    await _ack(bot, message, "✅ Sent to support.")


# ───────────────── Support: admin -> user ─────────────────
@admin_router.message(F.reply_to_message)
async def admin_reply(message: Message, bot: Bot):
    r = message.reply_to_message
    uid = _map.get((message.chat.id, r.message_id))
    if uid is None:  # fallback after a restart: read ID from the header message
        m = _ID_RE.search(r.text or "")
        if m:
            uid = int(m.group(1))
    if uid is None:
        return  # not a support thread
    try:
        await bot.copy_message(uid, message.chat.id, message.message_id)
        await _ack(bot, message, "✅ Delivered.")
    except TelegramForbiddenError:
        await message.answer("⚠️ This user has blocked the bot.")
    except TelegramAPIError as e:
        await message.answer(f"⚠️ Could not deliver: {e}")
