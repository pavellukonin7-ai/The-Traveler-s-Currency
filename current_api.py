"""Secure exchange-rate client for api.exchangerate.host."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests


CONVERT_ENDPOINT = "https://api.exchangerate.host/convert"


class ExchangeRateError(RuntimeError):
    """Raised when the provider cannot return a usable conversion."""


@dataclass(frozen=True)
class ConversionResult:
    from_currency: str
    to_currency: str
    amount: float
    result: float
    rate: float
    checked_at: str


def convert_currency(
    from_currency: str,
    to_currency: str,
    amount: float = 1.0,
    access_key: str = "",
    timeout: int = 15,
) -> ConversionResult:
    if not access_key:
        raise ExchangeRateError("Не указан ключ валютного API.")

    from_code = from_currency.strip().upper()
    to_code = to_currency.strip().upper()
    if len(from_code) != 3 or len(to_code) != 3:
        raise ExchangeRateError("Укажите корректные трёхбуквенные коды валют.")
    if amount <= 0:
        raise ExchangeRateError("Сумма должна быть больше нуля.")

    try:
        response = requests.get(
            CONVERT_ENDPOINT,
            params={
                "access_key": access_key,
                "from": from_code,
                "to": to_code,
                "amount": amount,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except requests.RequestException as exc:
        raise ExchangeRateError("Сервис курсов временно недоступен.") from exc
    except ValueError as exc:
        raise ExchangeRateError("Сервис курсов вернул некорректный ответ.") from exc

    if payload.get("success") is False:
        error = payload.get("error") or {}
        message = error.get("info") or error.get("message") or "Не удалось получить курс."
        raise ExchangeRateError(str(message))

    result = payload.get("result")
    info = payload.get("info") or {}
    rate = info.get("rate")
    try:
        source_amount = float(amount)
        converted = float(result)
        numeric_rate = float(rate) if rate is not None else converted / source_amount
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ExchangeRateError("Сервис курсов не вернул результат конвертации.") from exc

    if numeric_rate <= 0:
        raise ExchangeRateError("Получен некорректный валютный курс.")

    return ConversionResult(
        from_currency=from_code,
        to_currency=to_code,
        amount=source_amount,
        result=converted,
        rate=numeric_rate,
        checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )

