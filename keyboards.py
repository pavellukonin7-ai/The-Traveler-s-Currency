"""Telegram keyboards used by the premium interface."""

from __future__ import annotations

from telebot import types


BTN_WALLET = "💎 Мой кошелёк"
BTN_CONVERTER = "💱 Конвертер"
BTN_ADD_EXPENSE = "➕ Добавить расход"
BTN_ANALYTICS = "📊 Аналитика"
BTN_TRIPS = "✈️ Путешествия"
BTN_MORE = "⚙️ Ещё"

CATEGORIES = {
    "food": ("🍽", "Еда"),
    "transport": ("🚕", "Транспорт"),
    "hotel": ("🏨", "Жильё"),
    "shopping": ("🛍", "Покупки"),
    "fun": ("🎭", "Развлечения"),
    "other": ("📦", "Другое"),
}


def main_menu() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2,
        is_persistent=True,
        input_field_placeholder="Выберите действие",
    )
    markup.row(types.KeyboardButton(BTN_WALLET), types.KeyboardButton(BTN_CONVERTER))
    markup.row(types.KeyboardButton(BTN_ADD_EXPENSE), types.KeyboardButton(BTN_ANALYTICS))
    markup.row(types.KeyboardButton(BTN_TRIPS), types.KeyboardButton(BTN_MORE))
    return markup


def rate_confirm_menu() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Использовать курс", callback_data="rate:accept"),
        types.InlineKeyboardButton("✍️ Ввести свой", callback_data="rate:manual"),
    )
    return markup


def category_menu() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(f"{icon} {name}", callback_data=f"expense_cat:{key}")
        for key, (icon, name) in CATEGORIES.items()
    ]
    markup.add(*buttons)
    return markup


def note_menu() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Пропустить комментарий", callback_data="expense_note:skip"))
    return markup


def expense_confirm_menu() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Записать", callback_data="expense:yes"),
        types.InlineKeyboardButton("Отмена", callback_data="expense:no"),
    )
    return markup


def trips_menu(trips) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    for trip in trips:
        active = "●" if trip["active"] else "○"
        label = f"{active} {trip['origin_country']} → {trip['destination_country']}"
        markup.add(types.InlineKeyboardButton(label, callback_data=f"trip:{trip['id']}"))
    markup.add(types.InlineKeyboardButton("＋ Новое путешествие", callback_data="trip:new"))
    return markup


def more_menu() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔄 Обновить курс", callback_data="more:refresh"),
        types.InlineKeyboardButton("📤 Экспорт CSV", callback_data="more:export"),
        types.InlineKeyboardButton("↩️ Отменить расход", callback_data="more:undo"),
        types.InlineKeyboardButton("⚖️ Свой курс", callback_data="more:setrate"),
        types.InlineKeyboardButton("❓ Помощь", callback_data="more:help"),
    )
    return markup

