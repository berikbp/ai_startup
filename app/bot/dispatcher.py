from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.router import router


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    return dispatcher
