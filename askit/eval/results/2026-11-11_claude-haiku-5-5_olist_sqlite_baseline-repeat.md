# Evaluation: olist pack, claude-haiku-5-5, sqlite (baseline-repeat)

Run started 2026-11-11T18:39:26+00:00 with 49 questions from `packs/olist/eval/questions.yaml`.

**Accuracy: 39 of 49 (80%)**

| Category | Questions | Passed | Accuracy |
|---|---:|---:|---:|
| simple | 6 | 6 | 100% |
| aggregation | 7 | 6 | 86% |
| join_detail | 5 | 5 | 100% |
| date_time | 6 | 5 | 83% |
| ranking | 6 | 5 | 83% |
| complex | 8 | 3 | 38% |
| ambiguous | 3 | 1 | 33% |
| out_of_scope | 3 | 3 | 100% |
| adversarial | 5 | 5 | 100% |

## Cost and speed

- Outcomes: answered 37, blocked 4, declined 7, failed 1
- Response time: 2.4s average, 4.8s slowest, 120s total
- Tokens: 22,077 input, 10,855 output, 279,456 read from cache, 5,822 written to cache
- Estimated cost: $0.0112 ($0.00023 per question), list prices

## Failures

| Id | Category | Reason | Detail | Question |
|---|---|---|---|---|
| a03 | aggregation | wrong_result | no column matches reference column avg_review_score | What is the average review score? |
| d02 | date_time | wrong_result | 5 rows, expected 1 | Which month had the highest revenue? |
| r05 | ranking | wrong_result | 5 rows, expected 1 | Which customer state has the highest late delivery rate? |
| c01 | complex | wrong_result | 21 rows, expected 9 | What was the month-over-month revenue growth in 2018? |
| c03 | complex | wrongly_blocked | The query could not be parsed: Error tokenizing 'ate | What is the top product category by revenue in each of the 5 biggest customer states? |
| c04 | complex | error | no such column: seller_tier | What share of 2018 revenue came from Platinum tier sellers? |
| c06 | complex | wrongly_blocked | The query could not be parsed: Error tokenizing 's ON s.customer_unique_id = f.customer_unique_id' | On average, how many days pass between a customer's first and second order? |
| c07 | complex | wrongly_blocked | The query could not be parsed: Error tokenizing 'order_review_group | Do customers whose first order got a bad review (1 or 2) come back less often than those who gave 4 or 5? |
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
