"""The Traveler's Currency Premium Telegram bot."""

from __future__ import annotations

import html
import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import telebot
from telebot import types

import database
from config import SETTINGS
from country_currency import (
    SUPPORTED_COUNTRY_COUNT,
    CurrencyInfo,
    resolve_country_currency,
    resolve_currency_code,
)
from current_api import ConversionResult, ExchangeRateError, convert_currency
from exporter import expenses_csv
from formatters import money, parse_amount, progress_bar, rate_text
from keyboards import (
    BTN_ADD_EXPENSE,
    BTN_ANALYTICS,
    BTN_CONVERTER,
    BTN_MORE,
    BTN_TRIPS,
    BTN_WALLET,
    CATEGORIES,
    category_menu,
    expense_confirm_menu,
    main_menu,
    more_menu,
    note_menu,
    rate_confirm_menu,
    trips_menu,
)


logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("traveler_currency")

if not SETTINGS.telegram_bot_token:
    raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в файле .env")

bot = telebot.TeleBot(SETTINGS.telegram_bot_token, parse_mode="HTML")


class Step(str, Enum):
    ORIGIN = "origin"
    DESTINATION = "destination"
    MANUAL_RATE = "manual_rate"
    INITIAL_AMOUNT = "initial_amount"
    CHANGE_RATE = "change_rate"
    CONVERT_FROM = "convert_from"
    CONVERT_TO = "convert_to"
    CONVERT_AMOUNT = "convert_amount"
    EXPENSE_AMOUNT = "expense_amount"
    EXPENSE_NOTE = "expense_note"


@dataclass
class DraftTrip:
    origin: CurrencyInfo | None = None
    destination: CurrencyInfo | None = None
    rate: float | None = None
    rate_source: str = "api"
    rate_updated_at: str | None = None


@dataclass
class ConversionDraft:
    from_code: str | None = None
    to_code: str | None = None


@dataclass
class UserState:
    step: Step | None = None
    trip: DraftTrip = field(default_factory=DraftTrip)
    conversion: ConversionDraft = field(default_factory=ConversionDraft)


@dataclass
class PendingExpense:
    trip_id: int
    amount_destination: float
    amount_home: float
    category: str = "Другое"
    note: str = ""


states: dict[int, UserState] = {}
pending_expenses: dict[int, PendingExpense] = {}

OLD_BUTTONS = {
    "💰 Баланс": BTN_WALLET,
    "📊 История расходов": BTN_ANALYTICS,
    "📍 Новое путешествие": BTN_TRIPS,
    "🆕 Новое путешествие": BTN_TRIPS,
    "📋 Мои путешествия": BTN_TRIPS,
    "⚖️ Изменить курс": BTN_MORE,
    "🔄 Изменить курс": BTN_MORE,
    "◻️ Помощь": BTN_MORE,
    "ℹ️ Помощь": BTN_MORE,
}


def safe_answer(call: types.CallbackQuery, text: str | None = None) -> None:
    try:
        bot.answer_callback_query(call.id, text=text)
    except Exception:
        logger.debug("Callback already expired", exc_info=True)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def active_trip_or_warn(chat_id: int, user_id: int):
    trip = database.get_active_trip(user_id)
    if trip is None:
        bot.send_message(
            chat_id,
            "✈️ <b>Сначала создайте путешествие</b>\n\n"
            "Я сохраню маршрут, бюджет и валюту назначения.",
            reply_markup=trips_menu([]),
        )
    return trip


def fetch_conversion(from_code: str, to_code: str, amount: float = 1.0) -> ConversionResult:
    if from_code == to_code:
        return ConversionResult(from_code, to_code, amount, amount, 1.0, now_iso())
    return convert_currency(
        from_code,
        to_code,
        amount=amount,
        access_key=SETTINGS.exchange_rate_access_key,
    )


def send_home(chat_id: int, user_id: int, first_name: str = "") -> None:
    trip = database.get_active_trip(user_id)
    name = f", {html.escape(first_name)}" if first_name else ""
    if trip:
        text = (
            f"💎 <b>The Traveler’s Currency Premium</b>\n\n"
            f"Рады видеть вас{name}.\n"
            f"Активный маршрут: <b>{trip['origin_country']} → {trip['destination_country']}</b>\n\n"
            "Выберите действие в меню."
        )
    else:
        text = (
            f"💎 <b>The Traveler’s Currency Premium</b>\n\n"
            f"Добро пожаловать{name}. Я помогу контролировать бюджет поездки, "
            "конвертировать валюты и анализировать расходы.\n\n"
            f"Поддерживается {SUPPORTED_COUNTRY_COUNT} стран и территорий. "
            f"Нажмите <b>{BTN_TRIPS}</b>, чтобы начать."
        )
    bot.send_message(chat_id, text, reply_markup=main_menu())


def show_wallet(chat_id: int, user_id: int) -> None:
    trip = active_trip_or_warn(chat_id, user_id)
    if trip is None:
        return
    stats = database.trip_stats(user_id, trip["id"])
    spent = float(stats["spent_destination"] if stats else 0)
    initial = float(trip["initial_balance_destination"] or trip["balance_destination"] + spent)
    bar, percent = progress_bar(spent, initial)
    source = "онлайн" if trip["rate_source"] == "api" else "ваш курс"
    text = (
        "💎 <b>Кошелёк путешествия</b>\n"
        f"{trip['origin_country']} → {trip['destination_country']}\n\n"
        f"<b>{money(trip['balance_destination'])} {trip['destination_currency']}</b>\n"
        f"≈ {money(trip['balance_home'])} {trip['home_currency']}\n\n"
        f"Потрачено: <b>{money(spent)} {trip['destination_currency']}</b>\n"
        f"{bar} {percent:.0f}% бюджета\n\n"
        f"Курс ({source}): 1 {trip['home_currency']} = "
        f"{rate_text(float(trip['rate']))} {trip['destination_currency']}"
    )
    bot.send_message(chat_id, text, reply_markup=main_menu())


def show_analytics(chat_id: int, user_id: int) -> None:
    trip = active_trip_or_warn(chat_id, user_id)
    if trip is None:
        return
    stats = database.trip_stats(user_id, trip["id"])
    if not stats or stats["count"] == 0:
        bot.send_message(
            chat_id,
            "📊 <b>Аналитика расходов</b>\n\n"
            "Расходов пока нет. Добавьте первую покупку, и здесь появится сводка.",
            reply_markup=main_menu(),
        )
        return
    lines = [
        "📊 <b>Аналитика расходов</b>",
        f"{trip['origin_country']} → {trip['destination_country']}",
        "",
        f"Всего операций: <b>{stats['count']}</b>",
        f"Потрачено: <b>{money(stats['spent_destination'])} {trip['destination_currency']}</b>",
        f"≈ {money(stats['spent_home'])} {trip['home_currency']}",
        "",
        "<b>По категориям</b>",
    ]
    for row in stats["categories"]:
        icon = next((item[0] for item in CATEGORIES.values() if item[1] == row["category"]), "•")
        lines.append(f"{icon} {html.escape(row['category'])}: {money(row['total'])} {trip['destination_currency']}")

    recent = database.list_expenses(user_id, trip["id"], limit=5)
    lines.extend(["", "<b>Последние операции</b>"])
    for expense in recent:
        note = f" · {html.escape(expense['note'])}" if expense["note"] else ""
        lines.append(
            f"• {money(expense['amount_destination'])} {trip['destination_currency']} "
            f"— {html.escape(expense['category'])}{note}"
        )
    bot.send_message(chat_id, "\n".join(lines), reply_markup=main_menu())


def show_trips(chat_id: int, user_id: int) -> None:
    trips = database.list_trips(user_id)
    text = "✈️ <b>Ваши путешествия</b>\n\nВыберите маршрут или создайте новый."
    bot.send_message(chat_id, text, reply_markup=trips_menu(trips))


def start_new_trip(chat_id: int, user_id: int) -> None:
    states[user_id] = UserState(step=Step.ORIGIN)
    pending_expenses.pop(user_id, None)
    bot.send_message(
        chat_id,
        "✈️ <b>Новое путешествие · 1/4</b>\n\n"
        "Откуда вы отправляетесь?\n"
        "Введите страну на русском, английском или ISO-кодом.\n\n"
        "Например: <i>Россия, Brazil, JP</i>",
        reply_markup=main_menu(),
    )


def start_converter(chat_id: int, user_id: int) -> None:
    states[user_id] = UserState(step=Step.CONVERT_FROM)
    bot.send_message(
        chat_id,
        "💱 <b>Конвертер валют · 1/3</b>\n\n"
        "Введите исходную валюту или страну.\n"
        "Например: <i>RUB, Россия, EUR</i>",
        reply_markup=main_menu(),
    )


def start_expense(chat_id: int, user_id: int) -> None:
    trip = active_trip_or_warn(chat_id, user_id)
    if trip is None:
        return
    states[user_id] = UserState(step=Step.EXPENSE_AMOUNT)
    bot.send_message(
        chat_id,
        "➕ <b>Новый расход · 1/3</b>\n\n"
        f"Введите сумму в <b>{trip['destination_currency']}</b>.",
        reply_markup=main_menu(),
    )


def prepare_expense(chat_id: int, user_id: int, amount_destination: float) -> None:
    trip = active_trip_or_warn(chat_id, user_id)
    if trip is None:
        return
    pending_expenses[user_id] = PendingExpense(
        trip_id=int(trip["id"]),
        amount_destination=amount_destination,
        amount_home=amount_destination / float(trip["rate"]),
    )
    states.pop(user_id, None)
    bot.send_message(
        chat_id,
        "➕ <b>Новый расход · 2/3</b>\n\n"
        f"{money(amount_destination)} {trip['destination_currency']}\n"
        "Выберите категорию:",
        reply_markup=category_menu(),
    )


def show_expense_confirmation(chat_id: int, user_id: int) -> None:
    pending = pending_expenses.get(user_id)
    if pending is None:
        bot.send_message(chat_id, "Данные расхода устарели. Введите сумму ещё раз.", reply_markup=main_menu())
        return
    trip = database.get_trip(user_id, pending.trip_id)
    if trip is None:
        pending_expenses.pop(user_id, None)
        return
    note = f"\nКомментарий: {html.escape(pending.note)}" if pending.note else ""
    bot.send_message(
        chat_id,
        "➕ <b>Новый расход · 3/3</b>\n\n"
        f"Сумма: <b>{money(pending.amount_destination)} {trip['destination_currency']}</b>\n"
        f"Эквивалент: {money(pending.amount_home)} {trip['home_currency']}\n"
        f"Категория: {html.escape(pending.category)}{note}",
        reply_markup=expense_confirm_menu(),
    )


def ask_change_rate(chat_id: int, user_id: int) -> None:
    trip = active_trip_or_warn(chat_id, user_id)
    if trip is None:
        return
    states[user_id] = UserState(step=Step.CHANGE_RATE)
    bot.send_message(
        chat_id,
        "⚖️ <b>Свой курс</b>\n\n"
        f"Сейчас: 1 {trip['home_currency']} = {rate_text(trip['rate'])} {trip['destination_currency']}\n"
        "Введите новый курс положительным числом.",
        reply_markup=main_menu(),
    )


def show_help(chat_id: int) -> None:
    bot.send_message(
        chat_id,
        "❓ <b>Как пользоваться Premium</b>\n\n"
        f"<b>{BTN_WALLET}</b> — остаток и прогресс бюджета.\n"
        f"<b>{BTN_CONVERTER}</b> — конвертация любой валютной пары.\n"
        f"<b>{BTN_ADD_EXPENSE}</b> — расход с категорией и комментарием.\n"
        f"<b>{BTN_ANALYTICS}</b> — категории и последние операции.\n"
        f"<b>{BTN_TRIPS}</b> — создание и переключение поездок.\n"
        f"<b>{BTN_MORE}</b> — обновление курса, CSV и отмена расхода.\n\n"
        "Команда /cancel отменяет текущий ввод.",
        reply_markup=main_menu(),
    )


def handle_origin(message: types.Message, state: UserState) -> None:
    origin = resolve_country_currency(message.text or "")
    if origin is None:
        bot.send_message(message.chat.id, "Не нашёл страну. Например: <i>Россия, Germany, US</i>.")
        return
    state.trip.origin = origin
    state.step = Step.DESTINATION
    bot.send_message(
        message.chat.id,
        "✈️ <b>Новое путешествие · 2/4</b>\n\n"
        f"Отправление: <b>{origin.country} · {origin.code}</b>\n"
        "Куда вы едете?",
        reply_markup=main_menu(),
    )


def handle_destination(message: types.Message, state: UserState) -> None:
    destination = resolve_country_currency(message.text or "")
    if destination is None:
        bot.send_message(message.chat.id, "Не нашёл страну назначения. Попробуйте другое название.")
        return
    if state.trip.origin is None:
        start_new_trip(message.chat.id, message.from_user.id)
        return
    state.trip.destination = destination
    try:
        result = fetch_conversion(state.trip.origin.code, destination.code)
    except ExchangeRateError as exc:
        state.step = Step.MANUAL_RATE
        state.trip.rate_source = "manual"
        bot.send_message(
            message.chat.id,
            "Сейчас не удалось получить онлайн-курс.\n\n"
            f"Введите вручную: 1 {state.trip.origin.code} = ? {destination.code}\n"
            f"<i>{html.escape(str(exc))}</i>",
            reply_markup=main_menu(),
        )
        return
    state.trip.rate = result.rate
    state.trip.rate_source = "api"
    state.trip.rate_updated_at = result.checked_at
    bot.send_message(
        message.chat.id,
        "✈️ <b>Новое путешествие · 3/4</b>\n\n"
        f"Онлайн-курс: 1 {state.trip.origin.code} = "
        f"<b>{rate_text(result.rate)} {destination.code}</b>\n\n"
        "Использовать этот курс?",
        reply_markup=rate_confirm_menu(),
    )


def handle_manual_rate(message: types.Message, state: UserState) -> None:
    rate = parse_amount(message.text or "")
    if rate is None:
        bot.send_message(message.chat.id, "Введите курс положительным числом.")
        return
    state.trip.rate = rate
    state.trip.rate_source = "manual"
    state.trip.rate_updated_at = now_iso()
    state.step = Step.INITIAL_AMOUNT
    bot.send_message(
        message.chat.id,
        f"✈️ <b>Новое путешествие · 4/4</b>\n\nВведите бюджет в <b>{state.trip.origin.code}</b>.",
        reply_markup=main_menu(),
    )


def finish_trip(message: types.Message, state: UserState) -> None:
    amount = parse_amount(message.text or "")
    draft = state.trip
    if amount is None:
        bot.send_message(message.chat.id, "Введите бюджет положительным числом.")
        return
    if not draft.origin or not draft.destination or not draft.rate:
        start_new_trip(message.chat.id, message.from_user.id)
        return
    destination_amount = amount * draft.rate
    database.create_trip(
        message.from_user.id,
        draft.origin.country,
        draft.destination.country,
        draft.origin.code,
        draft.destination.code,
        draft.rate,
        draft.rate_source,
        amount,
        destination_amount,
        draft.rate_updated_at,
    )
    states.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        "✨ <b>Путешествие готово</b>\n\n"
        f"{draft.origin.country} → {draft.destination.country}\n"
        f"Бюджет: <b>{money(amount)} {draft.origin.code}</b>\n"
        f"Доступно: <b>{money(destination_amount)} {draft.destination.code}</b>\n\n"
        "Кошелёк, расходы и аналитика уже настроены.",
        reply_markup=main_menu(),
    )


def handle_converter_input(message: types.Message, state: UserState) -> None:
    if state.step == Step.CONVERT_FROM:
        code = resolve_currency_code(message.text or "")
        if code is None:
            bot.send_message(message.chat.id, "Не нашёл валюту. Введите код или страну, например USD или США.")
            return
        state.conversion.from_code = code
        state.step = Step.CONVERT_TO
        bot.send_message(message.chat.id, f"💱 <b>Конвертер · 2/3</b>\n\n{code} → какая валюта?")
        return
    if state.step == Step.CONVERT_TO:
        code = resolve_currency_code(message.text or "")
        if code is None:
            bot.send_message(message.chat.id, "Не нашёл валюту назначения. Попробуйте код, например EUR.")
            return
        state.conversion.to_code = code
        state.step = Step.CONVERT_AMOUNT
        bot.send_message(
            message.chat.id,
            f"💱 <b>Конвертер · 3/3</b>\n\n"
            f"{state.conversion.from_code} → {code}\nВведите сумму.",
        )
        return
    amount = parse_amount(message.text or "")
    if amount is None or not state.conversion.from_code or not state.conversion.to_code:
        bot.send_message(message.chat.id, "Введите сумму положительным числом.")
        return
    try:
        result = fetch_conversion(state.conversion.from_code, state.conversion.to_code, amount)
    except ExchangeRateError as exc:
        bot.send_message(message.chat.id, f"Не удалось выполнить конвертацию: {html.escape(str(exc))}")
        return
    states.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        "💱 <b>Результат конвертации</b>\n\n"
        f"{money(amount)} {result.from_currency}\n"
        f"= <b>{money(result.result)} {result.to_currency}</b>\n\n"
        f"1 {result.from_currency} = {rate_text(result.rate)} {result.to_currency}",
        reply_markup=main_menu(),
    )


@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message) -> None:
    send_home(message.chat.id, message.from_user.id, message.from_user.first_name or "")


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message: types.Message) -> None:
    states.pop(message.from_user.id, None)
    pending_expenses.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "Текущий ввод отменён.", reply_markup=main_menu())


@bot.message_handler(commands=["newtrip"])
def cmd_newtrip(message: types.Message) -> None:
    start_new_trip(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["balance", "wallet"])
def cmd_wallet(message: types.Message) -> None:
    show_wallet(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["history", "analytics"])
def cmd_analytics(message: types.Message) -> None:
    show_analytics(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["switch"])
def cmd_switch(message: types.Message) -> None:
    show_trips(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["setrate"])
def cmd_setrate(message: types.Message) -> None:
    ask_change_rate(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message) -> None:
    show_help(message.chat.id)


@bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("trip:")))
def trip_callback(call: types.CallbackQuery) -> None:
    safe_answer(call)
    if call.data == "trip:new":
        start_new_trip(call.message.chat.id, call.from_user.id)
        return
    try:
        trip_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    trip = database.set_active_trip(call.from_user.id, trip_id)
    if trip is None:
        bot.send_message(call.message.chat.id, "Путешествие не найдено.")
        return
    bot.send_message(
        call.message.chat.id,
        f"● Активный маршрут: <b>{trip['origin_country']} → {trip['destination_country']}</b>",
        reply_markup=main_menu(),
    )


@bot.callback_query_handler(func=lambda call: call.data in {"rate:accept", "rate:manual"})
def rate_callback(call: types.CallbackQuery) -> None:
    safe_answer(call)
    state = states.get(call.from_user.id)
    if not state or not state.trip.origin or not state.trip.destination:
        bot.send_message(call.message.chat.id, "Данные устарели. Начните создание путешествия заново.")
        return
    if call.data == "rate:manual":
        state.step = Step.MANUAL_RATE
        bot.send_message(
            call.message.chat.id,
            f"Введите курс: 1 {state.trip.origin.code} = ? {state.trip.destination.code}",
        )
        return
    state.step = Step.INITIAL_AMOUNT
    bot.send_message(
        call.message.chat.id,
        f"✈️ <b>Новое путешествие · 4/4</b>\n\nВведите бюджет в <b>{state.trip.origin.code}</b>.",
    )


@bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("expense_cat:")))
def category_callback(call: types.CallbackQuery) -> None:
    safe_answer(call)
    pending = pending_expenses.get(call.from_user.id)
    key = call.data.split(":", 1)[1]
    if pending is None or key not in CATEGORIES:
        bot.send_message(call.message.chat.id, "Данные расхода устарели. Введите сумму снова.")
        return
    pending.category = CATEGORIES[key][1]
    states[call.from_user.id] = UserState(step=Step.EXPENSE_NOTE)
    bot.send_message(
        call.message.chat.id,
        "Добавьте короткий комментарий, например <i>ужин</i> или <i>такси из аэропорта</i>.",
        reply_markup=note_menu(),
    )


@bot.callback_query_handler(func=lambda call: call.data == "expense_note:skip")
def skip_note_callback(call: types.CallbackQuery) -> None:
    safe_answer(call)
    states.pop(call.from_user.id, None)
    show_expense_confirmation(call.message.chat.id, call.from_user.id)


@bot.callback_query_handler(func=lambda call: call.data in {"expense:yes", "expense:no"})
def expense_callback(call: types.CallbackQuery) -> None:
    safe_answer(call)
    pending = pending_expenses.pop(call.from_user.id, None)
    states.pop(call.from_user.id, None)
    if call.data == "expense:no":
        bot.send_message(call.message.chat.id, "Расход отменён.", reply_markup=main_menu())
        return
    if pending is None:
        bot.send_message(call.message.chat.id, "Данные расхода устарели. Введите сумму снова.")
        return
    updated = database.add_expense(
        call.from_user.id,
        pending.trip_id,
        pending.amount_destination,
        pending.amount_home,
        pending.category,
        pending.note,
    )
    if updated is None:
        bot.send_message(call.message.chat.id, "Не удалось сохранить расход.")
        return
    bot.send_message(
        call.message.chat.id,
        "✅ <b>Расход записан</b>\n\n"
        f"{money(pending.amount_destination)} {updated['destination_currency']} · "
        f"{html.escape(pending.category)}\n"
        f"Остаток: <b>{money(updated['balance_destination'])} "
        f"{updated['destination_currency']}</b>",
        reply_markup=main_menu(),
    )


@bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("more:")))
def more_callback(call: types.CallbackQuery) -> None:
    safe_answer(call)
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    action = call.data.split(":", 1)[1]
    if action == "help":
        show_help(chat_id)
        return
    if action == "setrate":
        ask_change_rate(chat_id, user_id)
        return
    trip = active_trip_or_warn(chat_id, user_id)
    if trip is None:
        return
    if action == "refresh":
        try:
            result = fetch_conversion(trip["home_currency"], trip["destination_currency"])
        except ExchangeRateError as exc:
            bot.send_message(chat_id, f"Не удалось обновить курс: {html.escape(str(exc))}")
            return
        updated = database.update_trip_rate(
            user_id, trip["id"], result.rate, "api", result.checked_at
        )
        bot.send_message(
            chat_id,
            "🔄 <b>Курс обновлён</b>\n\n"
            f"1 {trip['home_currency']} = {rate_text(result.rate)} {trip['destination_currency']}\n"
            f"Баланс: {money(updated['balance_destination'])} {updated['destination_currency']}",
            reply_markup=main_menu(),
        )
        return
    if action == "undo":
        undone = database.undo_last_expense(user_id, trip["id"])
        if undone is None:
            bot.send_message(chat_id, "Нет расходов, которые можно отменить.")
            return
        expense, updated = undone
        bot.send_message(
            chat_id,
            "↩️ <b>Последний расход отменён</b>\n\n"
            f"Возвращено: {money(expense['amount_destination'])} {trip['destination_currency']}\n"
            f"Баланс: <b>{money(updated['balance_destination'])} {trip['destination_currency']}</b>",
            reply_markup=main_menu(),
        )
        return
    if action == "export":
        expenses = database.list_expenses(user_id, trip["id"], limit=None)
        if not expenses:
            bot.send_message(chat_id, "В этом путешествии пока нет расходов для экспорта.")
            return
        document = io.BytesIO(expenses_csv(trip, reversed(expenses)))
        document.name = f"expenses_trip_{trip['id']}.csv"
        bot.send_document(
            chat_id,
            document,
            caption="📤 История расходов в формате CSV",
            reply_markup=main_menu(),
        )


@bot.message_handler(content_types=["text"])
def text_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    text = (message.text or "").strip()
    action = OLD_BUTTONS.get(text, text)
    if action == BTN_WALLET:
        show_wallet(message.chat.id, user_id)
        return
    if action == BTN_CONVERTER:
        start_converter(message.chat.id, user_id)
        return
    if action == BTN_ADD_EXPENSE:
        start_expense(message.chat.id, user_id)
        return
    if action == BTN_ANALYTICS:
        show_analytics(message.chat.id, user_id)
        return
    if action == BTN_TRIPS:
        show_trips(message.chat.id, user_id)
        return
    if action == BTN_MORE:
        bot.send_message(message.chat.id, "⚙️ <b>Дополнительные действия</b>", reply_markup=more_menu())
        return

    state = states.get(user_id)
    if state:
        if state.step == Step.ORIGIN:
            handle_origin(message, state)
        elif state.step == Step.DESTINATION:
            handle_destination(message, state)
        elif state.step == Step.MANUAL_RATE:
            handle_manual_rate(message, state)
        elif state.step == Step.INITIAL_AMOUNT:
            finish_trip(message, state)
        elif state.step in {Step.CONVERT_FROM, Step.CONVERT_TO, Step.CONVERT_AMOUNT}:
            handle_converter_input(message, state)
        elif state.step == Step.EXPENSE_AMOUNT:
            amount = parse_amount(text)
            if amount is None:
                bot.send_message(message.chat.id, "Введите сумму положительным числом.")
            else:
                prepare_expense(message.chat.id, user_id, amount)
        elif state.step == Step.EXPENSE_NOTE:
            pending = pending_expenses.get(user_id)
            if pending:
                pending.note = text[:120]
            states.pop(user_id, None)
            show_expense_confirmation(message.chat.id, user_id)
        elif state.step == Step.CHANGE_RATE:
            new_rate = parse_amount(text)
            trip = database.get_active_trip(user_id)
            if new_rate is None:
                bot.send_message(message.chat.id, "Введите курс положительным числом.")
            elif trip:
                updated = database.update_trip_rate(user_id, trip["id"], new_rate, "manual", now_iso())
                states.pop(user_id, None)
                bot.send_message(
                    message.chat.id,
                    f"Курс обновлён: 1 {updated['home_currency']} = "
                    f"{rate_text(updated['rate'])} {updated['destination_currency']}",
                    reply_markup=main_menu(),
                )
        return

    amount = parse_amount(text)
    if amount is not None and database.get_active_trip(user_id):
        prepare_expense(message.chat.id, user_id, amount)
        return
    bot.send_message(
        message.chat.id,
        "Выберите действие в меню или используйте /help.",
        reply_markup=main_menu(),
    )


def main() -> None:
    database.init_db()
    bot.set_my_commands(
        [
            types.BotCommand("start", "Главное меню"),
            types.BotCommand("newtrip", "Новое путешествие"),
            types.BotCommand("wallet", "Мой кошелёк"),
            types.BotCommand("analytics", "Аналитика расходов"),
            types.BotCommand("cancel", "Отменить текущий ввод"),
            types.BotCommand("help", "Помощь"),
        ]
    )
    logger.info("The Traveler's Currency Premium started")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    main()

