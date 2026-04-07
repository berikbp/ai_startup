from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отправить номер телефона", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def confirmation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да, всё верно")],
            [KeyboardButton(text="Нет, начать заново")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
