from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, Message

from app.bot.ui.anchor_store import get_anchor_message_id, set_anchor_message_id


async def render_anchor_panel(
    message: Message,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> int:
    chat_id = message.chat.id
    anchor_id = await get_anchor_message_id(chat_id)

    if anchor_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=anchor_id,
                text=text,
                reply_markup=reply_markup,
            )
            return anchor_id
        except Exception:
            pass

    sent = await message.answer(text, reply_markup=reply_markup)
    await set_anchor_message_id(chat_id, sent.message_id)
    return sent.message_id
