# Evaluation: olist pack, claude-haiku-5-5, sqlite (keyword-k3)

Run started 2026-11-14T11:54:37+00:00 with 49 questions from `packs/olist/eval/questions.yaml`.

**Accuracy: 38 of 49 (78%)**

| Category | Questions | Passed | Accuracy |
|---|---:|---:|---:|
| simple | 6 | 6 | 100% |
| aggregation | 7 | 4 | 57% |
| join_detail | 5 | 5 | 100% |
| date_time | 6 | 3 | 50% |
| ranking | 6 | 5 | 83% |
| complex | 8 | 5 | 62% |
| ambiguous | 3 | 2 | 67% |
| out_of_scope | 3 | 3 | 100% |
| adversarial | 5 | 5 | 100% |

## Cost and speed

- Outcomes: answered 38, blocked 1, declined 8, failed 2
- Response time: 2.7s average, 7.7s slowest, 134s total
- Retries after a failed query (up to 1 per question): 5 questions retried, 1 of them then passed
- Schema retrieval: keyword, top 3 tables; every table the reference query needs was sent for 36 of 41 questions
- Tokens: 137,537 input, 13,170 output, 146,340 read from cache, 0 written to cache
- Estimated cost: $0.0218 ($0.00044 per question), list prices

## Failures

| Id | Category | Reason | Detail | Question |
|---|---|---|---|---|
| a02 | aggregation | wrongly_blocked | chatbot.v_monthly_trends_placeholder is not one of the tables Askit can query. | What was the average order value in 2018? |
| a06 | aggregation | error | no such column: freight_brl | What is the average freight cost per order? |
| a07 | aggregation | wrong_result | no column matches reference column late_rate_pct | What is the late delivery rate for delivered orders? |
| d02 | date_time | wrong_result | 5 rows, expected 1 | Which month had the highest revenue? |
| d05 | date_time | wrong_result | 2 rows, expected 1 | What share of revenue came from orders placed on weekends? |
| d06 | date_time | wrong_result | no column matches reference column avg_delivery_days | What was the average delivery time in days for delivered orders in each year? |
| r05 | ranking | wrong_result | 5 rows, expected 1 | Which customer state has the highest late delivery rate? |
| c01 | complex | wrong_result | 21 rows, expected 9 | What was the month-over-month revenue growth in 2018? |
| c04 | complex | error | no such column: seller_tier | What share of 2018 revenue came from Platinum tier sellers? |
| c07 | complex | wrong_result | 3 rows, expected 2 | Do customers whose first order got a bad review (1 or 2) come back less often than those who gave 4 or 5? |
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
