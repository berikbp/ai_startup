from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.router import build_router


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router())
    return dispatcher
