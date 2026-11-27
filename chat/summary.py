"""The order summary the bot shows after every change: the lines with their prices.

It is built from the order service's priced lines, so what the customer reads is what the server
computed. Names are in the conversation's language; amounts are integers in fils.
"""

from typing import Any

from orders.pricing import PricedOrder

from .texts import pick


def summary_payload(
    priced: PricedOrder, line_numbers: list[int], locale: str
) -> dict[str, Any]:
    """The ``summary`` of an ``order_summary`` message.

    ``line_numbers`` are the stored numbers of the priced lines, in the same order: the numbers
    shown are the ones the customer and the assistant use to address a line.
    """
    return {
        "lines": [
            {
                "line": number,
                "item_id": str(line.item_id),
                "name": pick(line.name_en, line.name_ar, locale),
                "options": [
                    {
                        "id": str(option.id),
                        "name": pick(option.name_en, option.name_ar, locale),
                        "price_delta_minor": option.price_delta_minor,
                    }
                    for option in line.options
                ],
                "quantity": line.quantity,
                "note": line.note or None,
                "unit_price_minor": line.unit_price_minor,
                "line_total_minor": line.line_total_minor,
            }
            for number, line in zip(line_numbers, priced.lines, strict=True)
        ],
        "subtotal_minor": priced.subtotal_minor,
        "total_minor": priced.total_minor,
        "currency": priced.currency,
    }
