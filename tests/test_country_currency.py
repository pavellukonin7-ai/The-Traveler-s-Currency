import unittest

from country_currency import (
    SUPPORTED_COUNTRY_COUNT,
    resolve_country_currency,
    resolve_currency_code,
)


class CountryCurrencyTests(unittest.TestCase):
    def test_catalog_and_aliases(self) -> None:
        self.assertGreaterEqual(SUPPORTED_COUNTRY_COUNT, 240)
        self.assertEqual(resolve_country_currency("Россия").code, "RUB")
        self.assertEqual(resolve_country_currency("Brazil").code, "BRL")
        self.assertEqual(resolve_country_currency("Côte d’Ivoire").code, "XOF")

    def test_currency_input_accepts_country_or_code(self) -> None:
        self.assertEqual(resolve_currency_code("США"), "USD")
        self.assertEqual(resolve_currency_code("eur"), "EUR")
        self.assertIsNone(resolve_currency_code("ZZZ"))


if __name__ == "__main__":
    unittest.main()

