# Projects

Hi, I'm **Daniyal Johri**, an Analytics Engineer.

I learn by doing. This repo is where I build things end to end, break them, fix them and write down what I learned along the way. Each project lives in its own folder, with its own README, and can be cloned and run on its own.

## Projects

| Project | What it is | Stack |
|---|---|---|
| [Olist Data Warehouse](olist_data_warehouse) | A medallion data warehouse on Brazilian e-commerce data, enriched with weather, exchange rates, holidays, population and macro data to test what drives late deliveries and bad reviews. | SQL Server, T-SQL |
| [Askit](askit) | Ask a database questions in plain English. Claude writes the SQL, a read-only login and query checks keep it safe, and a small data pack describes each database. Measured at 86 to 94% accuracy on 49 business questions. Runs on the Olist warehouse or a portable SQLite copy. | Python, FastAPI, Claude API, React, SQL Server, SQLite |

More to come.

## About Askit

[Askit](askit) answers business questions about a database in plain English, with the SQL behind every answer and an Excel download. It runs on the Olist Data Warehouse above, or on a single SQLite file for anyone without SQL Server.

- **Safe by design.** It connects with a read-only login, and every query is parsed and checked before it runs: one `SELECT`, approved tables only. Writes, other schemas and prompt injection were refused in every test run.
- **Works on other databases.** Everything Askit knows about a database lives in a small data pack, and `askit init` drafts one for a database it has never seen.
- **Measured, not just demonstrated.** 49 business questions with hand-checked reference SQL, scored by comparing result sets, every setting run twice:

  | Setup | Accuracy | Cost for all 49 questions |
  |---|---:|---:|
  | Default | 86 to 88% | about 1 US cent |
  | With a stronger model checking each answer | 94% | about 18 US cents |

- **What measuring taught me.** Feeding a failed query's error back once fixed most malformed SQL. A model checking its own answers approved its own mistakes, while a different, stronger model fixed them. Sending only the relevant tables didn't pay on a small database, so it's kept for large ones. A data pack reviewed with domain knowledge beat the auto-drafted one.

Details: [README](askit/README.md) · [Evaluation report](askit/docs/EVALUATION.md) · [Roadmap and scaling](askit/docs/ROADMAP.md). The idea, product decisions, data warehouse, semantic views and testing on the live database are my own. The code, tests and documentation, including the evaluations, were written with Claude; I reviewed, tested and committed every change.

## Connect

[LinkedIn](https://www.linkedin.com/in/daniyaljohri/) · [GitHub](https://github.com/daniyaljohri)
