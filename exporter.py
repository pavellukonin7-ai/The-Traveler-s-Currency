"""CSV export for trip expenses."""

from __future__ import annotations

import csv
import io


def expenses_csv(trip, expenses) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(
        [
            "Дата",
            "Категория",
            f"Сумма, {trip['destination_currency']}",
            f"Эквивалент, {trip['home_currency']}",
            "Комментарий",
        ]
    )
    for expense in expenses:
        writer.writerow(
            [
                expense["created_at"],
                expense["category"],
                f"{float(expense['amount_destination']):.2f}",
                f"{float(expense['amount_home']):.2f}",
                expense["note"] or "",
            ]
        )
    return stream.getvalue().encode("utf-8-sig")

