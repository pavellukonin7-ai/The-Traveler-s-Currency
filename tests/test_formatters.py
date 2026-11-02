import unittest

from formatters import money, parse_amount, progress_bar, rate_text


class FormatterTests(unittest.TestCase):
    def test_amount_parsing(self) -> None:
        self.assertEqual(parse_amount("1 250,50"), 1250.5)
        self.assertIsNone(parse_amount("ноль"))
        self.assertIsNone(parse_amount("-5"))

    def test_money_and_rate(self) -> None:
        self.assertEqual(money(1250.5), "1 250.50")
        self.assertEqual(rate_text(12.5), "12.5")

    def test_progress_is_capped_visually(self) -> None:
        bar, percent = progress_bar(120, 100)
        self.assertEqual(bar, "▓" * 10)
        self.assertEqual(percent, 120)


if __name__ == "__main__":
    unittest.main()

