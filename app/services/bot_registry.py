from __future__ import annotations

import uuid
from dataclasses import dataclass

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


@dataclass(slots=True)
class RegistryEntry:
    token: str
    bot: Bot


class BotRegistry:
    def __init__(self) -> None:
        self._entries: dict[uuid.UUID, RegistryEntry] = {}

    async def get_bot(self, *, clinic_id: uuid.UUID, token: str) -> Bot:
        entry = self._entries.get(clinic_id)
        if entry is not None and entry.token == token:
            return entry.bot

        if entry is not None:
            await entry.bot.session.close()

        bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._entries[clinic_id] = RegistryEntry(token=token, bot=bot)
        return bot

    async def invalidate(self, clinic_id: uuid.UUID) -> None:
        entry = self._entries.pop(clinic_id, None)
        if entry is not None:
            await entry.bot.session.close()

    async def close(self) -> None:
        entries = list(self._entries.values())
        self._entries.clear()
        for entry in entries:
            await entry.bot.session.close()
