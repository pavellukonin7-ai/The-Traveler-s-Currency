"""Resolve every ISO country or territory to its current primary currency.

Country names and legal-tender currencies come from Babel's local CLDR data.
No network requests are made here; exchange rates are still fetched exclusively
by ``current_api.py`` from api.exchangerate.host/convert.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from babel import Locale
from babel.numbers import get_currency_name, get_territory_currencies


@dataclass(frozen=True)
class CurrencyInfo:
    country: str
    code: str
    name: str


# CLDR lists more than one legal tender for a few countries. For a travel
# wallet, prefer the country's own currency over a parallel foreign currency.
PRIMARY_CURRENCY_OVERRIDES: dict[str, str] = {
    "BT": "BTN",  # Bhutan also accepts INR
    "LS": "LSL",  # Lesotho also uses ZAR
    "NA": "NAD",  # Namibia also uses ZAR
    "PA": "PAB",  # Panama also uses USD
    "SZ": "SZL",  # Eswatini also uses ZAR
}


# Common names that differ from CLDR's formal Russian/English country names.
EXTRA_ALIASES: dict[str, str] = {
    "англия": "GB",
    "британия": "GB",
    "великобритания": "GB",
    "рф": "RU",
    "российская федерация": "RU",
    "сша": "US",
    "штаты": "US",
    "оаэ": "AE",
    "эмираты": "AE",
    "южная корея": "KR",
    "северная корея": "KP",
    "корея": "KR",
    "чехия": "CZ",
    "тайвань": "TW",
    "лаос": "LA",
    "молдавия": "MD",
    "боливия": "BO",
    "венесуэла": "VE",
    "танзания": "TZ",
    "сирия": "SY",
    "иран": "IR",
    "вьетнам": "VN",
    "бруней": "BN",
    "кабо верде": "CV",
    "кот д ивуар": "CI",
    "конго": "CG",
    "демократическая республика конго": "CD",
    "д р конго": "CD",
    "палестина": "PS",
    "ватикан": "VA",
    "мьянма": "MM",
    "бирма": "MM",
    "македония": "MK",
    "северная македония": "MK",
    "косово": "XK",
    "usa": "US",
    "uk": "GB",
    "uae": "AE",
    "south korea": "KR",
    "north korea": "KP",
    "czech republic": "CZ",
    "ivory coast": "CI",
    "cape verde": "CV",
    "vatican": "VA",
    "vatican city": "VA",
    "east timor": "TL",
    "burma": "MM",
    "macedonia": "MK",
}


def normalize_country(value: str) -> str:
    """Normalize spelling, punctuation and accents for forgiving lookup."""

    text = unicodedata.normalize("NFKD", value.strip().casefold().replace("ё", "е"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _build_country_catalog() -> tuple[dict[str, CurrencyInfo], dict[str, CurrencyInfo]]:
    russian = Locale.parse("ru")
    english = Locale.parse("en")
    by_territory: dict[str, CurrencyInfo] = {}
    aliases: dict[str, CurrencyInfo] = {}

    for territory_code, russian_name in russian.territories.items():
        if len(territory_code) != 2 or not territory_code.isalpha() or territory_code == "ZZ":
            continue

        currency_codes = get_territory_currencies(territory_code, tender=True)
        if not currency_codes:
            continue

        preferred = PRIMARY_CURRENCY_OVERRIDES.get(territory_code)
        currency_code = preferred if preferred in currency_codes else currency_codes[0]
        currency_name = get_currency_name(currency_code, locale=russian)
        info = CurrencyInfo(str(russian_name), currency_code, str(currency_name))
        by_territory[territory_code] = info

        english_name = english.territories.get(territory_code)
        for alias in (russian_name, english_name, territory_code):
            if alias:
                aliases[normalize_country(str(alias))] = info

    for alias, territory_code in EXTRA_ALIASES.items():
        info = by_territory.get(territory_code)
        if info is not None:
            aliases[normalize_country(alias)] = info

    return by_territory, aliases


COUNTRIES_BY_CODE, COUNTRIES = _build_country_catalog()
SUPPORTED_COUNTRY_COUNT = len(COUNTRIES_BY_CODE)


def resolve_country_currency(value: str) -> CurrencyInfo | None:
    """Resolve a Russian/English country name or ISO alpha-2 country code."""

    return COUNTRIES.get(normalize_country(value))


def resolve_currency_code(value: str) -> str | None:
    """Resolve a country name or a known ISO 4217 code to the currency code."""

    cleaned = value.strip().upper()
    if cleaned in {info.code for info in COUNTRIES_BY_CODE.values()}:
        return cleaned
    info = resolve_country_currency(value)
    return info.code if info else None
