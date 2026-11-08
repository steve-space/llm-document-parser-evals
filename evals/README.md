# Evals

The unit tests check that the code runs. The evals check something different:
**does the parser extract the RIGHT values?**

## How it works

1. `cases.json` holds small documents together with the correct answer.
2. `run_evals.py` sends each document through the real parser.
3. `scoring.py` compares the answer with the correct one, field by field.
4. A report shows accuracy per case and per field.

Only fields listed in `expected` are scored. A field set to `null` means the
model must NOT invent a value.

## Run

    python -m evals.run_evals --fake     # free: a pretend perfect model, checks the eval itself
    python -m evals.run_evals            # real model, needs ANTHROPIC_API_KEY, costs a little money
    python -m evals.run_evals --min 0.9  # exit code 1 if accuracy is below 90 %

`--fake` must always give 100 %. If it does not, the cases or the scoring rules
have a bug, not the model.

## Add a case

Add an object with `name`, `text` and `expected` to `cases.json`. Good cases
are the ones where the model went wrong before.

## Not done yet

- The real-model run has not been executed (no API key was used while building this).
- Only 7 cases: enough to learn the method, too few to trust a score of 92 %.
- No comparison of line-item descriptions, only of amounts.
