"""Scoring: decide, field by field, whether the model's answer is correct.

Plain functions, no network, no model. That is on purpose: the scoring rules
must be simple and testable, because a wrong rule makes the whole eval lie.

Rules (kept deliberately small):
  * Only fields that appear in `expected` are scored.
  * Text fields: equal after trimming spaces and ignoring upper/lower case.
  * total_amount: equal if the numbers differ by less than 0.01.
  * line_items: equal if the list of amounts is the same (order does not matter).
    Descriptions are not compared, because the model may word them differently.
"""

NUMBER_TOLERANCE = 0.01


def _normalize_text(value):
    if value is None:
        return None
    return " ".join(str(value).split()).casefold()


def _numbers_equal(expected, actual) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    try:
        return abs(float(expected) - float(actual)) < NUMBER_TOLERANCE
    except (TypeError, ValueError):
        return False


def _amounts(items) -> list:
    """Sorted list of the 'amount' values of a line_items list (None counts as empty)."""
    if not items:
        return []
    amounts = []
    for item in items:
        if not isinstance(item, dict) or item.get("amount") is None:
            amounts.append(None)
        else:
            try:
                amounts.append(round(float(item["amount"]), 2))
            except (TypeError, ValueError):
                amounts.append(None)
    return sorted(amounts, key=lambda a: (a is None, a))


def score_field(field: str, expected, actual) -> bool:
    if field == "total_amount":
        return _numbers_equal(expected, actual)
    if field == "line_items":
        return _amounts(expected) == _amounts(actual)
    return _normalize_text(expected) == _normalize_text(actual)


def score_case(expected: dict, actual: dict) -> dict:
    """Return {field: True/False} for every field listed in `expected`."""
    actual = actual or {}
    return {field: score_field(field, value, actual.get(field)) for field, value in expected.items()}
