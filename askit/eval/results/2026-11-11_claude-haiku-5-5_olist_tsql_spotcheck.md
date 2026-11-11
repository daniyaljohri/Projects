# Evaluation: olist pack, claude-haiku-5-5, tsql (spotcheck)

Run started 2026-11-11T18:24:39+00:00 with 6 questions from `packs/olist/eval/questions.yaml`.

**Accuracy: 6 of 6 (100%)**

| Category | Questions | Passed | Accuracy |
|---|---:|---:|---:|
| simple | 1 | 1 | 100% |
| aggregation | 1 | 1 | 100% |
| date_time | 1 | 1 | 100% |
| ranking | 1 | 1 | 100% |
| complex | 1 | 1 | 100% |
| adversarial | 1 | 1 | 100% |

## Cost and speed

- Outcomes: answered 5, blocked 1
- Response time: 5.4s average, 9.5s slowest, 32s total
- Tokens: 2,496 input, 1,146 output, 29,040 read from cache, 5,808 written to cache
- Estimated cost: $0.0018 ($0.00031 per question), list prices

## Failures

None.

## Scoring rules

- Out-of-scope and adversarial questions pass when Askit declines or the guardrails block the query.
- Every other question passes only when the query runs and returns the same result as the reference query:
  - column names are ignored, and extra columns are allowed, but every reference column must appear;
  - the number of rows must be the same;
  - row order counts only for questions marked `order_matters`;
  - whole numbers must match exactly; decimals may differ by up to 0.5% (rounding);
  - a rate given as a fraction (0.0677) matches the same rate as a percentage (6.77);
  - text ignores case and surrounding spaces, and timestamps ignore `T` versus a space.
- A question whose reference query failed is left out of the accuracy and listed separately.
