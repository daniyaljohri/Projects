# Askit

Ask questions about a database in plain English and get answers backed by real SQL.

Askit turns a question into a SQL query with Claude, checks the query before it runs, executes it with a read-only login and explains the result in a sentence or two. Every answer shows the SQL behind it and can be downloaded to Excel.

It isn't tied to one database. Everything Askit knows about a database lives in a small **data pack** (three YAML files), and `askit init` drafts one for a database it has never seen. The first pack is the [Olist Data Warehouse](../olist_data_warehouse), which runs on SQL Server or, for anyone without SQL Server, a single SQLite file.

![Askit answering "Who are the top 10 sellers by revenue?"](docs/screenshot.png)

---

## At a glance

| | |
|---|---|
| Databases | SQL Server (main), SQLite (portable copy) |
| Model | Claude (Haiku tier by default, configurable) |
| Safety | Read-only login, SQL parsed and checked before it runs, row and time limits |
| Interfaces | Web UI (React), REST API (FastAPI), command line |
| Tests | 102 automated tests, no database or API key needed |
| Status | Phase 1 (engine) complete. Evaluation results are in progress. |

---

## How it works

```
question
  -> build the prompt     from the data pack: tables, columns, business rules, checked examples
  -> Claude writes SQL    structured output: run_query(sql) or decline(reason)
  -> guardrails           parse with sqlglot: one SELECT, allowed tables only
  -> run it               read-only login, 30 second timeout, 5,000 row cap
  -> explain it           a separate call that sees only the question and the rows
  -> log it               question, SQL, outcome, tokens and time
```

Every answer ends in one of four outcomes, shown in the UI and the logs:

| Outcome | Meaning |
|---|---|
| answered | the query ran and the result was explained |
| declined | Claude decided the data can't answer the question, so nothing ran |
| blocked | the guardrails rejected the query before it reached the database |
| failed | the database returned an error |

---

## How to run

### Prerequisites

- Python 3.11 or later
- An [Anthropic API key](https://console.anthropic.com/)
- For the web UI: Node.js 20.19 or later (or 22.12 or later)
- For the full setup: SQL Server 2017 or later with the [Olist Data Warehouse](../olist_data_warehouse) built

### 1. Install

```
cd askit
python -m venv venv
venv\Scripts\activate            (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           (macOS/Linux: cp .env.example .env)
```

Put your Anthropic API key in `.env`.

### 2. Connect a database

**Option A: SQLite, no SQL Server needed (quickest)**

Download `olist.sqlite.zip` from the [Releases page](https://github.com/daniyaljohri/Projects/releases), unzip it into `askit/data/`, and set these in `.env`:

```
ASKIT_DB_DIALECT=sqlite
ASKIT_DB_CONNECTION=data/olist.sqlite
```

**Option B: SQL Server, on the warehouse**

1. Build the [Olist Data Warehouse](../olist_data_warehouse).
2. Run the three scripts in `packs/olist/sql/` in SSMS, in order. The third one creates the `askit_reader` login and prints its password once. It needs SQL Server authentication (mixed mode) turned on.
3. Paste the password into `ASKIT_DB_CONNECTION` in `.env` (`PWD=`).

Then check the connection:

```
python -m askit check
```

It should list exactly the five `chatbot` views. The login can't see anything else.

### 3. Ask questions

```
python -m askit ask "Who are the top 10 sellers by revenue?"
python -m askit chat                 several questions, with follow-ups
```

### 4. Web UI

In one terminal:

```
python -m askit serve
```

In another:

```
cd ui
npm install
npm run dev
```

Then open http://localhost:3000.

### 5. Run the tests

```
python -m pytest
```

---

## Data packs

A data pack is everything Askit knows about one database. The engine has no database-specific code.

```
packs/olist/
├── pack.yaml        name, description, currency, date range, suggested questions
├── semantic.yaml    every table and column with its meaning, plus business rules
├── examples.yaml    checked question and SQL pairs, used as examples in the prompt
└── sql/             SQL Server setup: chatbot schema, semantic views, read-only login
```

The tables listed in `semantic.yaml` are also the guardrails' allow-list.

### Drafting a pack for a new database

```
python -m askit init --pack mydb --schema sales
```

`init` profiles every table the login can see (row counts, distinct values, null rates, ranges and common values), then asks Claude to draft descriptions, rules, examples and suggested questions. Column names and value lists always come from the database, not from the model, and a drafted example is kept only if it passes the guardrails and actually runs. `--no-llm` profiles only and leaves the descriptions to you.

A drafted pack is a starting point. On Olist, the draft got the table grains and data quirks right (it even caught a wrong end date in the hand-written pack), but it couldn't know business definitions such as churn thresholds or seller tiers, and one of its examples counted line items where it should have counted orders. Measuring that gap is part of the evaluation.

### The Olist views

Askit reads five views in a separate `chatbot` schema built on the warehouse's gold layer. The warehouse itself is untouched.

| View | Grain |
|---|---|
| `chatbot.v_orders_full` | one row per order line item, all dimensions joined |
| `chatbot.v_customer_summary` | one row per customer, with churn risk |
| `chatbot.v_seller_summary` | one row per seller, with seller tier |
| `chatbot.v_product_summary` | one row per product category |
| `chatbot.v_monthly_trends` | one row per month, with exchange rate and macro indicators |

---

## Design decisions

- **A semantic layer instead of raw tables.** The model reads views whose business rules are already applied: revenue is always price plus freight, and reviews, lateness and status are counted once per order, not once per line item. A query can be perfect SQL and still be wrong if the metric definitions are ambiguous, so the definitions are fixed in the views and spelled out in the pack.
- **Safety is enforced by the database, not the prompt.** Askit connects as `askit_reader`, which can `SELECT` from the `chatbot` schema and nothing else. `gold`, `silver` and `bronze` are explicitly denied, and the setup script checks this by impersonating the login. SQLite files are opened read-only.
- **Guardrails before the database.** Each query is parsed with `sqlglot` and must be a single `SELECT` that reads only the pack's tables. Writes, `SELECT INTO`, stacked statements, system catalogs, other databases, linked servers and `OPENROWSET` are rejected with a reason. The login is the wall; the guardrails give a clear reason, a log entry and a chance to stop bad SQL early.
- **Structured output instead of text parsing.** Claude must call one of two tools, `run_query(sql)` or `decline(reason)`, so there is no regex to pull SQL out of prose and no guessing whether a reply is a refusal.
- **The model never retypes numbers.** Tables in the UI and Excel come straight from the result rows. A second, stateless call writes one to three sentences about them and is told not to invent figures.
- **One pack, two databases.** When Askit opens a SQLite file it attaches it under the pack's schema names, so `chatbot.v_orders_full` works unchanged and the same pack, examples and guardrails serve both. Examples are translated between dialects with `sqlglot`.
- **No ORM.** The database layer uses `pyodbc` and `sqlite3` directly. An earlier version hung under the web server on Windows with SQLAlchemy and Windows authentication.

---

## Tests and checks

- **102 pytest tests** that need no database and no API key: guardrail rules (allowed and blocked queries for both dialects), the data pack (every example passes the guardrails and uses only documented columns), every Olist example translated to SQLite and run, the question pipeline with Claude replaced by a stand-in, the API, the Excel export, pack drafting and the SQLite export.
- **The view script checks itself**: row counts and revenue reconcile to the fact table, and each summary view has one row per key.
- **The login script checks itself**: it impersonates `askit_reader` and fails if the login can read the raw layers or has any write permission.
- **Evaluation** (in progress): a set of business questions with reference SQL, scored by comparing result sets, reported per category with cost and response time.

---

## Known limitations

- **Accuracy hasn't been measured yet.** That is the next phase. Until then, check the SQL behind any answer you rely on.
- **One question at a time.** The API handles requests on its main thread, because `pyodbc` with Windows authentication hung when called from worker threads.
- **Local use only.** There are no user accounts. Saved questions are kept in each browser, and conversations are kept in memory until the API restarts.
- **Result limits.** Queries stop after 30 seconds and 5,000 rows.
- **The fact table has 98,666 orders,** not the 99,441 in the raw Olist data. About 775 orders have no line items (mostly cancelled or unavailable), so they never reach a line-level fact, and the data ends on 2018-09-03.
- **Weather covers 13 cities,** about a third of orders, and is for the seller's city on the day the order was handed to the carrier.
- **Drafted packs need review.** `askit init` can't see business definitions that live outside the data.
- **Answers can vary** between runs and models, and each question costs two API calls.

---

## Data sources

The Olist data and the enrichment sources are described in [DATA_SOURCES.md](DATA_SOURCES.md), including the licence of the SQLite file.

---

## Repository structure

```
askit/
├── askit/                    the engine
│   ├── config.py             settings from .env
│   ├── db.py                 SQL Server and SQLite connections
│   ├── guardrails.py         query checks with sqlglot
│   ├── pack.py               data pack loading
│   ├── prompt.py             system prompt built from the pack
│   ├── llm.py                Claude calls
│   ├── pipeline.py           question to answer
│   ├── api.py                FastAPI endpoints
│   ├── export.py             Excel export
│   ├── feedback.py           answer ratings
│   ├── introspect.py         schema profiling
│   ├── onboard.py            data pack drafting
│   ├── sqlite_export.py      SQLite copy of a pack
│   └── cli.py                check, prompt, ask, chat, serve, init, export-sqlite
├── packs/olist/              the Olist data pack and its SQL Server setup scripts
├── tests/                    pytest
├── ui/                       React chat interface (Vite)
├── docs/                     screenshot
├── .env.example
├── requirements.txt
├── DATA_SOURCES.md
└── README.md
```

---

## Author

**Daniyal Johri**, Analytics Engineer
[GitHub](https://github.com/daniyaljohri) · [LinkedIn](https://www.linkedin.com/in/daniyaljohri/)

First version built April to September 2026 and rebuilt as a generic engine in November 2026. The idea, product decisions, data warehouse, semantic views and testing on the live database are my own. The Python and React code, tests and documentation were written with Claude (Anthropic); I reviewed, tested and committed every change.
