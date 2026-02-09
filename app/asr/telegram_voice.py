from __future__ import annotations

from aiogram import Bot


async def download_voice_bytes(bot: Bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    file_stream = await bot.download_file(file.file_path)
    return await file_stream.read()
