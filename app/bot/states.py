from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    WAITING_SERVICE = State()
    WAITING_DATETIME = State()
    WAITING_NAME = State()
    WAITING_PHONE = State()
    CONFIRMING = State()


class CancelStates(StatesGroup):
    CONFIRMING_CANCEL = State()
