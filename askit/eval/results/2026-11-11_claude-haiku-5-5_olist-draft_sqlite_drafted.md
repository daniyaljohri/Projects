# Evaluation: olist_draft pack, claude-haiku-5-5, sqlite (drafted)

Run started 2026-11-11T18:36:25+00:00 with 49 questions from `packs/olist/eval/questions.yaml`.

**Accuracy: 37 of 49 (76%)**

| Category | Questions | Passed | Accuracy |
|---|---:|---:|---:|
| simple | 6 | 6 | 100% |
| aggregation | 7 | 5 | 71% |
| join_detail | 5 | 5 | 100% |
| date_time | 6 | 4 | 67% |
| ranking | 6 | 3 | 50% |
| complex | 8 | 5 | 62% |
| ambiguous | 3 | 1 | 33% |
| out_of_scope | 3 | 3 | 100% |
| adversarial | 5 | 5 | 100% |

## Cost and speed

- Outcomes: answered 39, blocked 3, declined 7
- Response time: 2.4s average, 5.1s slowest, 120s total
- Tokens: 21,683 input, 10,485 output, 328,080 read from cache, 6,835 written to cache
- Estimated cost: $0.0115 ($0.00024 per question), list prices

## Failures

| Id | Category | Reason | Detail | Question |
|---|---|---|---|---|
| a03 | aggregation | wrong_result | no column matches reference column avg_review_score | What is the average review score? |
| a07 | aggregation | wrong_result | no column matches reference column late_rate_pct | What is the late delivery rate for delivered orders? |
| d05 | date_time | wrong_result | 2 rows, expected 1 | What share of revenue came from orders placed on weekends? |
| d06 | date_time | wrong_result | no column matches reference column avg_delivery_days | What was the average delivery time in days for delivered orders in each year? |
| r03 | ranking | wrong_result | no column matches reference column product_category | Which 5 product categories have the best average review score? |
| r04 | ranking | wrong_result | no column matches reference column seller_id | Which 5 sellers have the highest late delivery rate? |
| r05 | ranking | wrong_result | 5 rows, expected 1 | Which customer state has the highest late delivery rate? |
| c01 | complex | wrong_result | no column matches reference column growth_pct | What was the month-over-month revenue growth in 2018? |
| c03 | complex | wrongly_blocked | The query could not be parsed: Error tokenizing 'ate | What is the top product category by revenue in each of the 5 biggest customer states? |
| c07 | complex | wrongly_blocked | The query could not be parsed: Error tokenizing 'Y first_review_group | Do customers whose first order got a bad review (1 or 2) come back less often than those who gave 4 or 5? |
| m01 | ambiguous | wrong_result | 3 rows, expected 1 | How many orders did we get last month? |
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
