# Roadmap

What's next for Askit, roughly in order of value for effort, and how to set it up for databases much larger than Olist. Results that motivate each item are in [EVALUATION.md](EVALUATION.md).

## Done

| Phase | What | Result |
|---|---|---|
| 1 | Generic engine, guardrails, data packs, web UI, Excel export, SQLite copy | Merged, released as `askit-v0.1.0` |
| 2 | Evaluation: 49 questions, result-set scoring, curated vs drafted pack | 41 and 39 of 49; drafted pack 37 |
| 3 | Retry on SQL error | 42 and 43 of 49; on by default |
| 3 | Schema retrieval (keyword, embedding, hybrid) | No gain on five views, higher cost; off by default, kept for large schemas |
| 3 | Result self-check | Same model: accepted every answer. Sonnet as checker: 46 and 46 of 49 (94%), none made worse, about 15 times the cost; optional, off by default |

## Next steps

### Phase 4: a public benchmark

Run Askit on a subset of a public text-to-SQL benchmark (BIRD or Spider): SQLite databases it has never seen, onboarded only with `askit init`. This is the honest check that the engine is generic and not tuned to Olist, gives numbers comparable with published work, and is where schema retrieval and value lookup should show their value. Work: a loader that turns each benchmark database and its questions into a pack and a question file, then the existing runner and scorer.

### Phase 5: comparing Claude models

Run the same 49 questions with Haiku, Sonnet and Opus (`python -m askit eval --model ...`) for an accuracy, cost and speed table. No code needed; roughly $0.25 per Sonnet run and $0.50 per Opus run at current list prices. The question Phase 3 raised: is Haiku writing with Sonnet checking (94%, $0.18 a run) better value than Sonnet doing everything?

### Accuracy

The remaining failures are reasoning slips, not broken SQL. Ideas, each to be measured like the rest:

- **Make the Sonnet check cheaper.** It costs about 15 times as much because it reviews every answer, and most answers are already right. Askit can't know which answers are wrong (there's no reference answer in real use), but it can run the check only when a cheap signal suggests trouble: a "which ..." question with more than one row, a year in the question and other years in the result, a long multi-step query, or a query that needed a retry. Measure what share of the gain survives.
- **Checks in code.** Cheap rules that need no model, for the same signals, either as the gate above or on their own.
- **Example store from feedback.** The UI already records 👍 and 👎. Reviewed 👍 answers become examples, 👎 answers become evaluation questions, so Askit learns from use. Once there are more examples than fit in a prompt, pick the most similar ones per question. Keep examples that closely match evaluation questions out of the store, or the score stops meaning anything.
- **Value lookup.** Map what people type to what's stored ("São Paulo" to `sao paulo`, a misspelt category to the real one) using the column values the pack profile already holds. Little effect on Olist, where a pack rule covers it; more on unfamiliar databases.
- **Glossary.** Business terms and their definitions, added to the prompt when a question uses them.
- **Raw tables against semantic views.** Run the questions on the warehouse's gold star schema instead of the `chatbot` views, to measure how much the semantic layer itself adds.

### Product

- Several users at once: authentication, per-user sessions, a worker that doesn't block the API (the current single-thread design works around a `pyodbc` issue with Windows authentication).
- Hosting, with the read-only login and guardrails unchanged.
- More databases: PostgreSQL and Snowflake need one small backend each in `db.py`; `sqlglot` already handles the dialects.

## Scaling to larger databases

Guidance drawn from the Olist measurements and how prompt caching is priced. These are starting points to measure, not tested thresholds: Olist has five views, so the large-schema case itself is untested (that's Phase 4).

### When to turn on schema retrieval

Sending the whole schema works while it fits comfortably in one prompt, and on Olist it was both cheaper and more accurate. Turn retrieval on when either is true:

- **The schema no longer fits well.** As a rough guide, beyond 30 to 50 tables or a few tens of thousands of tokens of descriptions, the prompt gets expensive, slow and harder for the model to use well.
- **Retrieval would cost less.** A cached prompt is read at about a tenth of the normal input price, and the tables chosen per question can't be cached. So retrieval only saves money once the tables it sends are smaller than about a tenth of the full schema, after allowing for the fixed part of the prompt, which still caches. Check that the fixed part (instructions, rules, examples) is above the model's minimum cacheable length, or nothing caches at all.

### How to configure it

1. Make sure the descriptions are good. Both keyword and embedding search work over the pack's descriptions, so draft them with `askit init` and review them; a reviewed pack beat the drafted one by four or more questions on Olist.
2. Use hybrid retrieval (`ASKIT_SCHEMA_RETRIEVAL=hybrid`, with `requirements-retrieval.txt` installed). Keywords catch exact names and codes, embeddings catch different wording, and fusion covers each one's blind spots.
3. Choose the number of tables with `python -m askit retrieval-check`, before spending anything on full runs: raise `ASKIT_SCHEMA_TOP_K` until every table the reference queries need is retrieved for at least 95% of questions. A missing table makes the model invent names.
4. Then run `askit eval` twice with and without retrieval, and compare accuracy and cost, as in the evaluation.

### Beyond that

| Size | Approach |
|---|---|
| Fits in one cached prompt (Olist) | Send everything; retrieval off |
| Up to a few hundred tables | Hybrid retrieval, top K chosen by recall |
| Hundreds of tables, or very wide tables | Two stages: hybrid retrieval shortlists 20 to 30 tables, then Claude picks the final few; also trim columns on wide tables |
| Tens of thousands of searchable items (columns, values, examples) | Store the vectors in an index instead of comparing in memory: sqlite-vec, pgvector, or SQL Server 2025's `VECTOR` type |

Below that last size an index adds moving parts and no speed: comparing a question against a few thousand vectors in memory takes milliseconds.
