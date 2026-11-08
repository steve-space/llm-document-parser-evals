"""Run the eval: does the parser extract the RIGHT values, not just plausible ones?

Usage (from the project folder):

    python -m evals.run_evals --fake     # no API key, no cost: checks the eval itself
    python -m evals.run_evals            # real model (needs ANTHROPIC_API_KEY, costs money)
    python -m evals.run_evals --min 0.9  # exit with an error if accuracy is below 90 %

Steps:  load cases  ->  ask the parser  ->  score each field  ->  print a report.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.parser import ExtractionError, extract_structured_data
from app.schemas import DEFAULT_SCHEMA
from evals.scoring import score_case

CASES_PATH = Path(__file__).parent / "cases.json"


def load_cases(path: Path = CASES_PATH) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(cases: list, client=None, schema: dict = DEFAULT_SCHEMA) -> list:
    """Run every case through the parser. Never stops on one bad answer."""
    results = []
    for case in cases:
        try:
            actual = extract_structured_data(case["text"], schema, client=client)
            error = None
        except ExtractionError as exc:
            actual, error = {}, str(exc)
        results.append(
            {
                "name": case["name"],
                "scores": score_case(case["expected"], actual),
                "actual": actual,
                "error": error,
            }
        )
    return results


def summarize(results: list) -> dict:
    """Count correct / total per field and overall."""
    per_field = {}
    for result in results:
        for field, ok in result["scores"].items():
            correct, total = per_field.get(field, (0, 0))
            per_field[field] = (correct + int(ok), total + 1)
    correct_all = sum(c for c, _ in per_field.values())
    total_all = sum(t for _, t in per_field.values())
    return {
        "per_field": per_field,
        "correct": correct_all,
        "total": total_all,
        "accuracy": correct_all / total_all if total_all else 0.0,
    }


def print_report(results: list, summary: dict) -> None:
    print("\nPer case")
    for result in results:
        wrong = [f for f, ok in result["scores"].items() if not ok]
        status = "OK " if not wrong and not result["error"] else "BAD"
        detail = ""
        if result["error"]:
            detail = "  (model did not return valid JSON)"
        elif wrong:
            detail = "  wrong: " + ", ".join(wrong)
        print(f"  [{status}] {result['name']}{detail}")

    print("\nPer field")
    for field, (correct, total) in summary["per_field"].items():
        print(f"  {field:<15} {correct}/{total}")

    print(f"\nOverall: {summary['correct']}/{summary['total']} fields correct "
          f"= {summary['accuracy']:.0%}")


class _FakeClient:
    """A pretend model that answers every case perfectly (copies the expected answer).

    It exists to test the EVAL itself: with a perfect model the score must be 100 %.
    If it is not, the eval (cases or scoring) has a bug, not the model.
    """

    def __init__(self, cases: list):
        self._cases = cases
        self.messages = self

    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        for case in self._cases:
            if case["text"] in prompt:
                reply = json.dumps(case["expected"])
                break
        else:
            reply = "{}"
        block = type("Block", (), {"type": "text", "text": reply})()
        return type("Response", (), {"content": [block]})()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the document parser.")
    parser.add_argument("--fake", action="store_true", help="use a pretend perfect model (free)")
    parser.add_argument("--min", type=float, default=0.8, help="minimum accuracy, default 0.8")
    args = parser.parse_args(argv)

    cases = load_cases()
    client = None
    if args.fake:
        client = _FakeClient(cases)
        print("Mode: FAKE model (checks the eval itself, not the real model)")
    else:
        from app.config import settings

        if not settings.anthropic_api_key:
            print("No ANTHROPIC_API_KEY set. Set it in .env, or use --fake.")
            return 2
        print(f"Mode: REAL model ({settings.llm_model})")

    results = evaluate(cases, client=client)
    summary = summarize(results)
    print_report(results, summary)

    if summary["accuracy"] < args.min:
        print(f"\nFAILED: accuracy {summary['accuracy']:.0%} is below the minimum {args.min:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
