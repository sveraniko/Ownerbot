from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

LEGEND_MESSAGE_ID_KEY = "legend_message_id"
PANEL_MESSAGE_ID_KEY = "panel_message_id"
EPHEMERAL_MESSAGE_IDS_KEY = "ephemeral_message_ids"

NAV_BUTTON_TEXTS = {
    "📚 Шаблоны",
    "⚙️ Системы",
    "🔌 Upstream",
    "🧰 Tools",
    "🆘 Help",
    "Системы",
}


async def delete_message_safe(bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        return


async def delete_user_nav_message(message: Message) -> None:
    if message.text not in NAV_BUTTON_TEXTS:
        return
    await delete_message_safe(message.bot, message.chat.id, message.message_id)


async def cleanup_ephemerals(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    message_ids = data.get(EPHEMERAL_MESSAGE_IDS_KEY, [])
    if not isinstance(message_ids, list):
        message_ids = []
    for message_id in message_ids:
        try:
            parsed_id = int(message_id)
        except (TypeError, ValueError):
            continue
        await delete_message_safe(bot, chat_id, parsed_id)
    await state.update_data({EPHEMERAL_MESSAGE_IDS_KEY: []})


async def register_ephemeral_message(state: FSMContext, message_id: int) -> None:
    data = await state.get_data()
    message_ids = data.get(EPHEMERAL_MESSAGE_IDS_KEY, [])
    if not isinstance(message_ids, list):
        message_ids = []
    if message_id not in message_ids:
        message_ids.append(message_id)
    await state.update_data({EPHEMERAL_MESSAGE_IDS_KEY: message_ids})


async def show_panel(message: Message, state: FSMContext, text: str, *, reply_markup=None) -> int:
    data = await state.get_data()
    panel_message_id = data.get(PANEL_MESSAGE_ID_KEY)
    if panel_message_id is not None:
        try:
            panel_id = int(panel_message_id)
        except (TypeError, ValueError):
            panel_id = None
        if panel_id is not None:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=panel_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return panel_id
            except TelegramBadRequest:
                await delete_message_safe(message.bot, message.chat.id, panel_id)

    sent = await message.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
    await state.update_data({PANEL_MESSAGE_ID_KEY: sent.message_id})
    return sent.message_id


def preserve_anchors(data: dict) -> dict:
    preserved: dict[str, int] = {}
    for key in (LEGEND_MESSAGE_ID_KEY, PANEL_MESSAGE_ID_KEY):
        value = data.get(key)
        if value is not None:
            preserved[key] = value
    return preserved


async def clear_state_preserving_ui_anchors(state: FSMContext) -> None:
    data = await state.get_data()
    anchors = preserve_anchors(data)
    await state.clear()
    if anchors:
        await state.update_data(anchors)

