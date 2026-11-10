# Askit

Ask questions about a database in plain English and get answers backed by real SQL.

Askit turns a question into a SQL query with Claude, checks the query before it runs, executes it with a read-only login and explains the result. It is built to work on any database you describe with a small "data pack". The first pack is the [Olist Data Warehouse](../olist_data_warehouse).

**Status:** work in progress. Setup steps, evaluation results and limitations will be added as each part is finished.

## Built on

This project reads from the gold layer of [olist_data_warehouse](../olist_data_warehouse). Build that first.
