import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BROADCAST_RATE
from db import DB

log = logging.getLogger("broadcast")
running = False  # only one broadcast at a time


def build_kb(buttons) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    b = InlineKeyboardBuilder()
    for label, url in buttons:
        b.button(text=label, url=url)
    b.adjust(1)  # one button per row
    return b.as_markup()


async def send_payload(bot: Bot, chat_id: int, p: dict):
    kb = build_kb(p.get("buttons"))
    kind = p.get("type")
    if kind == "photo":
        return await bot.send_photo(chat_id, p["file_id"], caption=p["text"], reply_markup=kb)
    if kind == "video":
        return await bot.send_video(chat_id, p["file_id"], caption=p["text"], reply_markup=kb)
    return await bot.send_message(
        chat_id,
        p["text"],
        reply_markup=kb,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def _send_one(bot: Bot, uid: int, payload: dict) -> str:
    for _ in range(3):
        try:
            await send_payload(bot, uid, payload)
            return "ok"
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            return "blocked"
        except TelegramBadRequest as e:
            m = str(e).lower()
            if "chat not found" in m or "deactivated" in m:
                return "blocked"
            log.warning("bad request for %s: %s", uid, e)
            return "failed"
        except TelegramAPIError:
            await asyncio.sleep(1)  # network/server hiccup -> retry
        except Exception as e:
            log.warning("send error for %s: %s", uid, e)
            return "failed"
    return "failed"


async def run_broadcast(bot: Bot, db: DB, admin_id: int, payload: dict):
    global running
    running = True
    sent = blocked_n = failed = 0
    started = time.monotonic()
    try:
        status = await bot.send_message(admin_id, "📤 Broadcast started...")
        async for page in db.iter_active_pages():
            newly_blocked: list[int] = []
            for i in range(0, len(page), BROADCAST_RATE):
                chunk = page[i : i + BROADCAST_RATE]
                t0 = time.monotonic()
                results = await asyncio.gather(*(_send_one(bot, u, payload) for u in chunk))
                for uid, res in zip(chunk, results):
                    if res == "ok":
                        sent += 1
                    elif res == "blocked":
                        blocked_n += 1
                        newly_blocked.append(uid)
                    else:
                        failed += 1
                # pace: at most BROADCAST_RATE messages per second
                spare = 1.0 - (time.monotonic() - t0)
                if spare > 0:
                    await asyncio.sleep(spare)
            if newly_blocked:
                await db.set_blocked(newly_blocked, True)
            try:
                await status.edit_text(
                    f"📤 Broadcasting...\n✅ Sent: {sent}\n🚫 Blocked: {blocked_n}\n⚠️ Failed: {failed}"
                )
            except Exception:
                pass
        mins = (time.monotonic() - started) / 60
        await bot.send_message(
            admin_id,
            f"✅ <b>Broadcast finished</b> in {mins:.1f} min\n\n"
            f"✅ Sent: {sent}\n🚫 Blocked/deleted: {blocked_n}\n⚠️ Failed: {failed}",
        )
    except Exception as e:
        log.exception("broadcast crashed")
        try:
            await bot.send_message(admin_id, f"❌ Broadcast crashed: {e}\nSent so far: {sent}")
        except Exception:
            pass
    finally:
        running = False
