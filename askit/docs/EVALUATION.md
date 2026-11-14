# Evaluation

How accurate Askit is, how that was measured, and what each change to the pipeline did to it. The headline numbers are in the [README](../README.md#evaluation); this page has the detail. Every run listed here is committed in [`eval/results/`](../eval/results/) and can be re-scored without an API key:

```
python -m askit eval-report eval/results/<run>.jsonl
```

All runs use Claude Haiku 5.5 on the SQLite copy of the Olist warehouse, November 2026, unless stated otherwise.

---

## 1. Method

### Questions

49 questions in [`packs/olist/eval/questions.yaml`](../packs/olist/eval/questions.yaml):

| Category | Questions | What it tests |
|---|---:|---|
| simple | 6 | one view, one count or filter |
| aggregation | 7 | totals and averages, including per-order averages |
| join_detail | 5 | filters and breakdowns on the line-level view |
| date_time | 6 | months, years, a single day, a month with no orders |
| ranking | 6 | top N, with minimum volumes for rates and averages |
| complex | 8 | window functions, CTE chains, views joined to each other |
| ambiguous | 3 | underspecified questions with one chosen interpretation |
| out_of_scope | 3 | questions the data can't answer |
| adversarial | 5 | writes, other schemas, system tables, prompt injection, stacked statements |

The 41 answerable questions have reference SQL in T-SQL, checked by hand in SSMS against the warehouse's known figures (98,666 orders, revenue by year, the state with the highest late-delivery rate). Several are deliberate traps: counting orders rather than line items, a late rate per delivered order, a month with no orders, and a ranking where positions 10 and 11 tie (cut to a top 5 so the answer is unambiguous).

### Scoring

Askit's result is compared with the reference result, not the SQL text:

- column names are ignored and extra columns are allowed, but every reference column must appear;
- the number of rows must match;
- row order counts only for questions marked `order_matters`;
- whole numbers must match exactly; decimals may differ by up to 0.5%;
- a rate given as a fraction (0.0677) matches the same rate as a percentage (6.77);
- text ignores case and surrounding spaces, and timestamps ignore `T` versus a space (SQL Server and SQLite format them differently).

Out-of-scope and adversarial questions pass only when Askit declines or the guardrails block the query. A question whose reference query fails is reported separately and left out of the accuracy.

These rules were agreed before the first real run and have not been changed since. Two baseline failures (a "which month" question answered with five rows, the right one first) would pass under a looser row rule; loosening it after seeing the results would have been moving the goalposts.

### Running

Each question is asked once, without conversation history, through the same pipeline the web UI uses. The reference query runs on the same database. Each run writes one JSON line per question (generated SQL, both result sets, outcome, tokens, time, and the settings) and a markdown summary.

### Noise

Claude doesn't give identical answers on every run. Two runs of the same setup differed by two questions, so with 49 questions a difference of one or two (two to four percentage points) is not meaningful. Every setting that mattered was run twice.

---

## 2. Baseline (Phase 2)

| Run | Pack | Accuracy | Complex | Cost |
|---|---|---:|---:|---:|
| Baseline | curated `olist` | 41 / 49 (84%) | 4 / 8 | $0.011 |
| Baseline, repeat | curated `olist` | 39 / 49 (80%) | 3 / 8 | $0.011 |
| Drafted pack | `olist_draft`, unedited `askit init` output | 37 / 49 (76%) | 5 / 8 | $0.012 |
| SQL Server spot check | curated, 6 questions across the categories | 6 / 6 | 1 / 1 | $0.002 |

Simple, join, out-of-scope and adversarial questions were right in every run. Eight failures repeated in both curated runs:

| Question | What happened |
|---|---|
| a03 average review score | averaged over line items instead of orders (4.03 instead of 4.10) |
| d02, r05 "which month / which state" | the right answer in row 1, followed by four runners-up |
| c01 month-over-month growth in 2018 | calculated it for 2017 as well |
| c03, c07 multi-step queries | the SQL ended with a stray `"`, could not be parsed and was blocked |
| c04 Platinum sellers' share | used the seller tier on the orders view, where it doesn't exist |
| m03 "Is the business growing?" | a sensible answer, but not the January to August comparison the reference uses |

### What a reviewed pack adds

The drafted pack failed five questions the curated pack answered correctly in both runs. Four map to a rule written into the curated pack: late rate and delivery time per delivered order rather than per line item (the drafted pack's own example teaches the per-item version), and minimum volumes for rankings by a rate or average (without them a category with 14 sales and sellers with one late order top the lists). The fifth was a model slip. The drafted pack did no worse on complex questions, which fail for reasons a pack can't fix.

---

## 3. Improvements tested (Phase 3)

Each change was added on its own, run twice where it mattered, and kept on only if it helped by more than the noise.

| Setup | Accuracy | Complex | Cost per run | Time per answer | Decision |
|---|---:|---:|---:|---:|---|
| Baseline | 41, 39 | 4, 3 | $0.011 | 2.3 s | |
| **Retry on SQL error** | **42, 43** | **6, 6** | $0.012 | 2.6 s | **on by default** |
| + schema retrieval, hybrid, top 3 tables | 42, 39 | 6, 6 | $0.021 | 2.7 s | off by default |
| + schema retrieval, keyword, top 3 tables | 38 | 5 | $0.022 | 2.7 s | off |
| + schema retrieval, hybrid, all 5 tables | 41 | 6 | $0.027 | 2.8 s | layout check only |
| + result self-check, same model (Haiku) | 42, 42 | 6, 6 | $0.019 | 3.7 s | not useful |
| **+ result self-check by Sonnet** | **46, 46** | **6, 6** | **$0.18** | **5.1 s** | **recommended option, off by default** |

### Retry on SQL error

When the SQL can't be parsed or the database rejects it, the error goes back to Claude once and the corrected query runs. Safety blocks (writes, other schemas, system tables, stacked statements) and lost connections are never retried, so the guardrails can't be turned into hints.

Across the two runs five queries were retried. The stray-quote failures on c03 and c06 were fixed and correct all four times. c07 ran after its retry but grouped customers into four review bands instead of two, still wrong. Complex questions rose from 3 to 4 of 8 to 6 of 8 in both runs, for about 10% more cost. Adversarial questions stayed at 5 of 5.

### Schema retrieval

Instead of sending every table, Askit can send only the ones most relevant to the question: keyword ranking (BM25), a small local embedding model (`BAAI/bge-small-en-v1.5` through fastembed, ONNX, no PyTorch), or both merged by reciprocal rank fusion. `askit retrieval-check` measures, without an API key, how often every table a question's reference query reads was retrieved:

| Method | Top 1 | Top 2 | Top 3 | Top 4 | Top 5 |
|---|---:|---:|---:|---:|---:|
| keyword | 46% | 76% | 88% | 90% | 100% |
| embedding | 32% | 49% | 59% | 68% | 100% |
| hybrid | 37% | 59% | 88% | 93% | 100% |

Findings:

- **Standard keyword settings bury wide tables.** BM25 normally discounts long documents, but a table's description is long because it has many columns, not because it rambles. With the standard setting (b = 0.75) every miss was the 40-column orders view. The discount was weakened to b = 0.3 on that principle rather than by picking the best score (0.75 gave 80% at top 3, 0.5 and 0.3 gave 88%, 0 gave 90%).
- **Embeddings alone prefer the summary views**, whose columns (`total_orders`, `total_revenue_brl`) sit close in meaning to typical questions. Recall here is pessimistic: it asks for the table the reference query uses, and several "misses" could be answered from a summary view.
- **A missing table makes the model guess.** With keyword retrieval one question got no orders view and the model invented `v_monthly_trends_placeholder`; another used the orders view without having seen it and guessed a column name that doesn't exist.
- **Fewer tables cost accuracy on two questions even when the right table was sent.** d06 and r02 failed in both hybrid top-3 runs and in none of the retry runs. With all five tables in the same prompt layout they passed, so the cause is the left-out tables, not the layout; the summary views' descriptions ("average review per order", "late deliveries over delivered orders") seem to reinforce the grain rules.
- **On a small schema retrieval costs more.** The full prompt is cached and read at a tenth of the input price. With retrieval the tables chosen for each question can't be cached, and the fixed part alone is under the minimum length Claude caches for this model. Cost rose by 75% to 125%.

Retrieval stays in the engine for schemas too large to send in full, off by default. See [ROADMAP.md](ROADMAP.md#scaling-to-larger-databases) for when to turn it on.

### Result self-check

After a query runs, a second Claude call sees the question, the SQL and the shape of the result (row count, columns, the first rows) with a short general checklist (period and filters, one row versus a list, the level of calculation, the columns), and either accepts the result or writes a corrected query, which goes through the guardrails again. A correction that can't run never replaces a working answer.

**Checked by the same model (Haiku)** it accepted all 82 answers across two runs and revised none, including "which month" answered with five rows and "growth in 2018" answered with 21 rows. Accuracy was unchanged (42 and 42) at about 55% more cost. A model reviewing its own answer tends to agree with it: the reasoning that produced the slip also approves it.

**Checked by a stronger model (Sonnet 5.5, `ASKIT_CHECK_MODEL`)**, with Haiku still writing the SQL and the same checklist word for word, accuracy rose to 46 and 46 of 49 (94%). It revised 6 and 9 answers, turned 3 and 4 wrong answers into right ones, and turned none of the right answers wrong; the other revisions reworded correct queries without changing the result. It fixed the per-order average (a03) that had failed in every earlier run, cut the "which month" and "which state" answers to one row (d02, r05) in both runs, and fixed the grouping in c07 in one run. Every category except complex and ambiguous was at 100% in both runs.

The price is about 15 times the cost per run ($0.0037 per question instead of $0.00025) and twice the time per answer (about 5 seconds). The setting is off by default so Askit stays cheap and works with any API key; if the check model is unavailable, the check fails visibly and the original answer stands.

Sonnet 5.5 doesn't accept a forced tool call (`tool_choice` "any"), which Askit used to guarantee structured output. Askit now falls back to `tool_choice` "auto" when a model refuses, and treats a reply without a tool call as an error.

---

## 4. Where it stands

| Configuration | Accuracy | Cost per 49 questions | Time per answer |
|---|---:|---:|---:|
| Default: retry on, retrieval and self-check off | 42, 43 of 49 (86% to 88%) | about $0.012 | 2.6 s |
| Recommended for accuracy: plus self-check by Sonnet | 46, 46 of 49 (94%) | about $0.18 | 5.1 s |

Every unsafe or out-of-scope request was refused in every run.

With the default configuration the failures that remain are reasoning slips rather than broken SQL: an average over line items instead of orders (a03), extra rows for "which one" questions (d02, r05), a period wider than asked (c01), the wrong grouping (c07), and an ambiguous question answered in a different shape (m03). The Sonnet check fixes the first three. What's left with it is c01 (the right months, but the growth figures still differ), c07 in one run, and m03.

## 5. Limits of this evaluation

- 49 questions is a small set, and the questions were written alongside the curated pack, so they may favour its rules. A public benchmark on databases Askit has never seen is the planned check (Phase 4).
- One writing model (Haiku), plus Sonnet as a checker. Results on SQL Server were spot-checked on six questions, not run in full.
- With 49 questions one question is two points, and runs vary by about two questions.
- Ambiguous questions are scored against one chosen interpretation.
- Schema retrieval was tested on five views. Its real purpose, schemas too large to send in full, is not tested by Olist.
