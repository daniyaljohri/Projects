# Evaluation: olist pack, claude-haiku-5-5, sqlite (hybrid-k5)

Run started 2026-11-14T12:03:41+00:00 with 49 questions from `packs/olist/eval/questions.yaml`.

**Accuracy: 41 of 49 (84%)**

| Category | Questions | Passed | Accuracy |
|---|---:|---:|---:|
| simple | 6 | 6 | 100% |
| aggregation | 7 | 6 | 86% |
| join_detail | 5 | 5 | 100% |
| date_time | 6 | 4 | 67% |
| ranking | 6 | 5 | 83% |
| complex | 8 | 6 | 75% |
| ambiguous | 3 | 1 | 33% |
| out_of_scope | 3 | 3 | 100% |
| adversarial | 5 | 5 | 100% |

## Cost and speed

- Outcomes: answered 41, declined 8
- Response time: 2.8s average, 8.2s slowest, 138s total
- Retries after a failed query (up to 1 per question): 3 questions retried, 2 of them then passed
- Schema retrieval: hybrid, BAAI/bge-small-en-v1.5, top 5 tables; every table the reference query needs was sent for 41 of 41 questions
- Tokens: 187,825 input, 13,394 output, 138,210 read from cache, 2,710 written to cache
- Estimated cost: $0.0272 ($0.00056 per question), list prices

## Failures

| Id | Category | Reason | Detail | Question |
|---|---|---|---|---|
| a03 | aggregation | wrong_result | no column matches reference column avg_review_score | What is the average review score? |
| d02 | date_time | wrong_result | 5 rows, expected 1 | Which month had the highest revenue? |
| d05 | date_time | wrong_result | 2 rows, expected 1 | What share of revenue came from orders placed on weekends? |
| r05 | ranking | wrong_result | 5 rows, expected 1 | Which customer state has the highest late delivery rate? |
| c01 | complex | wrong_result | 21 rows, expected 9 | What was the month-over-month revenue growth in 2018? |
| c07 | complex | wrong_result | 3 rows, expected 2 | Do customers whose first order got a bad review (1 or 2) come back less often than those who gave 4 or 5? |
| m01 | ambiguous | wrong_result | no column matches reference column total_orders | How many orders did we get last month? |
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
