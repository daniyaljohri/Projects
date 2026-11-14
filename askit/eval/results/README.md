# Evaluation runs

Every evaluation run, in the order it was made. Each `.jsonl` file has one line for the run's settings and one per question (generated SQL, both result sets, outcome, tokens, time); the `.md` beside it is the summary. Method and analysis: [docs/EVALUATION.md](../../docs/EVALUATION.md).

Re-score any run without an API key or a database:

```
python -m askit eval-report eval/results/<run>.jsonl
```

All runs: Claude Haiku 5.5 writes the SQL, 49 questions from `packs/olist/eval/questions.yaml` (the spot check: 6 of them).

| Run | Pack | Database | Retries | Schema retrieval | Self-check | Accuracy | Complex | Cost | Time per answer |
|---|---|---|---:|---|---|---:|---:|---:|---:|
| [baseline](2026-11-11_claude-haiku-5-5_olist_sqlite_baseline.md) | olist | SQLite | 0 | off | off | 41 / 49 | 4 / 8 | $0.011 | 2.2 s |
| [baseline-repeat](2026-11-11_claude-haiku-5-5_olist_sqlite_baseline-repeat.md) | olist | SQLite | 0 | off | off | 39 / 49 | 3 / 8 | $0.011 | 2.4 s |
| [drafted](2026-11-11_claude-haiku-5-5_olist-draft_sqlite_drafted.md) | olist_draft | SQLite | 0 | off | off | 37 / 49 | 5 / 8 | $0.011 | 2.4 s |
| [spotcheck](2026-11-11_claude-haiku-5-5_olist_tsql_spotcheck.md) | olist | SQL Server | 0 | off | off | 6 / 6 | 1 / 1 | $0.002 | 5.4 s |
| [retry](2026-11-14_claude-haiku-5-5_olist_sqlite_retry.md) | olist | SQLite | 1 | off | off | 42 / 49 | 6 / 8 | $0.013 | 2.7 s |
| [retry-repeat](2026-11-14_claude-haiku-5-5_olist_sqlite_retry-repeat.md) | olist | SQLite | 1 | off | off | 43 / 49 | 6 / 8 | $0.012 | 2.6 s |
| [hybrid-k3](2026-11-14_claude-haiku-5-5_olist_sqlite_hybrid-k3.md) | olist | SQLite | 1 | hybrid, top 3 | off | 42 / 49 | 6 / 8 | $0.021 | 2.6 s |
| [hybrid-k3-repeat](2026-11-14_claude-haiku-5-5_olist_sqlite_hybrid-k3-repeat.md) | olist | SQLite | 1 | hybrid, top 3 | off | 39 / 49 | 6 / 8 | $0.021 | 2.7 s |
| [keyword-k3](2026-11-14_claude-haiku-5-5_olist_sqlite_keyword-k3.md) | olist | SQLite | 1 | keyword, top 3 | off | 38 / 49 | 5 / 8 | $0.022 | 2.7 s |
| [hybrid-k5](2026-11-14_claude-haiku-5-5_olist_sqlite_hybrid-k5.md) | olist | SQLite | 1 | hybrid, top 5 | off | 41 / 49 | 6 / 8 | $0.027 | 2.8 s |
| [selfcheck](2026-11-14_claude-haiku-5-5_olist_sqlite_selfcheck.md) | olist | SQLite | 1 | off | on, Haiku 5.5 | 42 / 49 | 6 / 8 | $0.019 | 3.6 s |
| [selfcheck-repeat](2026-11-14_claude-haiku-5-5_olist_sqlite_selfcheck-repeat.md) | olist | SQLite | 1 | off | on, Haiku 5.5 | 42 / 49 | 6 / 8 | $0.018 | 3.7 s |
| [sonnet-check](2026-11-14_claude-haiku-5-5_olist_sqlite_sonnet-check.md) | olist | SQLite | 1 | off | on, Sonnet 5.5 | 46 / 49 | 6 / 8 | $0.175 | 5.1 s |
| [sonnet-check-repeat](2026-11-14_claude-haiku-5-5_olist_sqlite_sonnet-check-repeat.md) | olist | SQLite | 1 | off | on, Sonnet 5.5 | 46 / 49 | 6 / 8 | $0.186 | 5.2 s |

Runs before 14 November predate the retry, retrieval and self-check settings; they ran with all three off.
