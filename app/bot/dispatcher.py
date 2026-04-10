from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseEventIsolation, BaseStorage

from app.bot.router import build_router


def build_dispatcher(
    *,
    storage: BaseStorage | None = None,
    events_isolation: BaseEventIsolation | None = None,
) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage, events_isolation=events_isolation)
    dispatcher.include_router(build_router())
    return dispatcher
