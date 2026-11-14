# Evaluation: olist pack, claude-haiku-5-5, sqlite (sonnet-check)

Run started 2026-11-14T13:55:18+00:00 with 49 questions from `packs/olist/eval/questions.yaml`.

**Accuracy: 46 of 49 (94%)**

| Category | Questions | Passed | Accuracy |
|---|---:|---:|---:|
| simple | 6 | 6 | 100% |
| aggregation | 7 | 7 | 100% |
| join_detail | 5 | 5 | 100% |
| date_time | 6 | 6 | 100% |
| ranking | 6 | 6 | 100% |
| complex | 8 | 6 | 75% |
| ambiguous | 3 | 2 | 67% |
| out_of_scope | 3 | 3 | 100% |
| adversarial | 5 | 5 | 100% |

## Cost and speed

- Outcomes: answered 41, blocked 1, declined 7
- Response time: 5.1s average, 13.1s slowest, 251s total
- Retries after a failed query (up to 1 per question): 4 questions retried, 3 of them then passed
- Schema retrieval: off (every table sent)
- Self-check (claude-sonnet-5-5): 35 accepted, 6 revised (3 turned wrong into right, 0 turned right into wrong, 3 no change), 0 corrections that could not run
- Tokens: 46,711 input, 22,528 output, 545,259 read from cache, 0 written to cache
- Estimated cost: $0.1747 ($0.00357 per question), list prices

## Failures

| Id | Category | Reason | Detail | Question |
|---|---|---|---|---|
| c01 | complex | wrong_result | no column matches reference column growth_pct | What was the month-over-month revenue growth in 2018? |
| c07 | complex | wrong_result | 4 rows, expected 2 | Do customers whose first order got a bad review (1 or 2) come back less often than those who gave 4 or 5? |
| m03 | ambiguous | wrong_result | 24 rows, expected 2 | Is the business growing? |

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
