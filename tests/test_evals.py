"""Tests for the eval itself. If these fail, the eval cannot be trusted."""
import json

from evals.run_evals import _FakeClient, evaluate, load_cases, summarize
from evals.scoring import score_case, score_field


def test_every_case_has_the_needed_keys():
    for case in load_cases():
        assert {"name", "text", "expected"} <= set(case)


def test_text_ignores_case_and_extra_spaces():
    assert score_field("vendor", "Acme Ltd", "  acme   LTD ")


def test_number_allows_tiny_difference_but_not_big_one():
    assert score_field("total_amount", 65.5, 65.50)
    assert not score_field("total_amount", 65.5, 56.5)


def test_null_must_stay_null():
    """The model must not invent a value when the document has none."""
    assert score_field("document_date", None, None)
    assert not score_field("document_date", None, "2026-01-01")


def test_line_items_compared_by_amount_not_order():
    expected = [{"amount": 40.0}, {"amount": 25.5}]
    actual = [{"description": "x", "amount": 25.5}, {"description": "y", "amount": 40}]
    assert score_field("line_items", expected, actual)


def test_only_listed_fields_are_scored():
    scores = score_case({"vendor": "A"}, {"vendor": "A", "currency": "USD"})
    assert list(scores) == ["vendor"]


def test_perfect_model_scores_100_percent():
    cases = load_cases()
    summary = summarize(evaluate(cases, client=_FakeClient(cases)))
    assert summary["accuracy"] == 1.0


def test_bad_model_scores_lower():
    class _WrongClient(_FakeClient):
        def create(self, **kwargs):
            block = type("Block", (), {"type": "text", "text": json.dumps({"vendor": "Wrong"})})()
            return type("Response", (), {"content": [block]})()

    cases = load_cases()
    summary = summarize(evaluate(cases, client=_WrongClient(cases)))
    assert summary["accuracy"] < 0.5


def test_invalid_json_counts_as_failure_but_does_not_crash():
    class _GarbageClient(_FakeClient):
        def create(self, **kwargs):
            block = type("Block", (), {"type": "text", "text": "not json"})()
            return type("Response", (), {"content": [block]})()

    cases = load_cases()
    results = evaluate(cases, client=_GarbageClient(cases))
    assert all(r["error"] for r in results)
    assert summarize(results)["accuracy"] < 1.0
