# The Traveler's Currency

Telegram-бот на Python и `pytelegrambotapi`: миникошелёк путешественника с локальным SQLite-хранилищем и курсами через реальный API `api.exchangerate.host`.

## Настройка

1. Установите зависимости:

```bash
pip install -r requirements.txt
```

2. Откройте `config.py` и заполните две переменные:

```python
EXCHANGE_RATE_ACCESS_KEY = "ваш_access_key_exchangerate_host"
TELEGRAM_BOT_TOKEN = "ваш_telegram_token"
```

3. Запустите бота:

```bash
python bot.py
```

## Что умеет бот

- Создаёт несколько путешествий для каждого пользователя.
- Хранит валютную пару, курс и баланс в двух валютах.
- Конвертирует начальную сумму через `http://api.exchangerate.host/convert`.
- Позволяет принять API-курс или вручную ввести курс местного обменника.
- Любое число в активном путешествии считает расходом в валюте назначения.
- Показывает inline-меню без обязательных slash-команд.
- Поддерживает `/newtrip`, `/switch`, `/balance`, `/history`, `/setrate`.

Все запросы к валютному API идут только через `current_api.py` и только на endpoint `/convert`.

