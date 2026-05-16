# Olist Data Warehouse Project (Olist_DWP)

A production-grade **medallion architecture data warehouse** built on SQL Server using the Brazilian Olist e-commerce dataset, enriched with five external data sources to answer senior-level business questions that go well beyond standard sales reporting.

> **Portfolio goal:** Most public Olist projects stop at basic revenue aggregations. This project layers macro-economic context, real weather conditions, and public holiday data on top of the core dataset to analyse how external conditions drive delivery performance, customer satisfaction, and seller behaviour simultaneously.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Dataset Sources](#dataset-sources)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Medallion Layer Design](#medallion-layer-design)
  - [Bronze Layer](#bronze-layer)
  - [Silver Layer](#silver-layer)
  - [Gold Layer](#gold-layer)
- [Star Schema](#star-schema)
- [Key Design Decisions](#key-design-decisions)
- [Performance](#performance)
- [How to Run](#how-to-run)
- [What Makes This Different](#what-makes-this-different)

---

## Project Overview

| Item | Detail |
|---|---|
| **Dataset** | Brazilian Olist e-commerce (Kaggle) — ~100K orders, 2016–2018 |
| **Database** | SQL Server 2025 Express Edition |
| **Architecture** | Medallion — Bronze / Silver / Gold |
| **Gold grain** | One row per order line item |
| **Fact rows** | 112,650 |

The central business question this warehouse is designed to answer:

> *"How do external conditions — weather, public holidays, exchange rate volatility, and macroeconomic stress — interact with seller location, product category, and delivery performance to predict customer satisfaction?"*

---

## Architecture

```
External Sources          Source Systems (Simulated)
      │                          │
      ▼                          ▼
┌─────────────────────────────────────────┐
│              BRONZE LAYER               │
│  Raw ingestion — no transformations     │
│  9 core tables (Python / pyodbc)        │
│  5 enrichment tables (BULK INSERT)      │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│              SILVER LAYER               │
│  Cleaned, typed, standardised           │
│  14 tables — stored procedure load      │
│  Delivery metrics computed here         │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│               GOLD LAYER                │
│  Star schema — business-ready           │
│  5 dimension views + 1 physical fact    │
│  MERGE-based incremental load           │
│  13 nonclustered indexes                │
└─────────────────────────────────────────┘
```

Architecture, data flow, and star schema diagrams are in `/Docs`.

---

## Dataset Sources

### Core Olist (Kaggle)

| Table | Simulated Source System | Description |
|---|---|---|
| `olist_orders_dataset` | OMS | Order lifecycle and status |
| `olist_order_items_dataset` | ERP | Line items, prices, freight |
| `olist_customers_dataset` | CRM | Customer records |
| `olist_sellers_dataset` | CRM | Seller records |
| `olist_products_dataset` | ERP | Product catalogue |
| `olist_order_payments_dataset` | OMS / Finance | Payment records |
| `olist_order_reviews_dataset` | Customer Feedback | Review scores and comments |
| `olist_geolocation_dataset` | CRM / Logistics | Zip code coordinates |
| `product_category_name_translation` | ERP | Portuguese → English category names |

### Enrichment Sources

| Source | Data | Join Key |
|---|---|---|
| [Open-Meteo](https://open-meteo.com/) | Daily weather (temp, rain, wind) for 13 Brazilian cities, 2016–2018 | Seller city + carrier dispatch date |
| [FRED DEXBZUS](https://fred.stlouisfed.org/series/DEXBZUS) | BRL/USD exchange rate — daily, forward-filled for weekends | Order purchase date |
| [World Bank](https://data.worldbank.org/) | Brazil GDP, inflation, unemployment, GDP per capita — annual | Order year |
| [IBGE](https://www.ibge.gov.br/) | Municipal population estimates | Customer/seller state + city |
| [Nager.Date](https://date.nager.at/) | Brazilian public holidays | Order purchase date |

---

## Tech Stack

| Tool | Purpose |
|---|---|
| SQL Server 2025 Express | Database engine |
| SSMS | All SQL authoring and execution |
| Python (pyodbc, pandas) | Bronze ingestion for RFC 4180 CSVs and weather download |
| draw.io | Architecture diagrams, star schema, data flow |
| Notion | Sprint planning and task tracking |
| GitHub | Version control and portfolio hosting |

---

## Repository Structure

```
Olist_DWP/
│
├── Datasets/
│   ├── Core/
│   │   ├── CRM/          # Customers, sellers, geolocation
│   │   ├── ERP/          # Products, order items, category translations
│   │   └── OMS/          # Orders, reviews, payments
│   └── Enrichment/       # Weather, FX rates, population, holidays, macro
│
├── Scripts/
│   ├── Bronze/
│   │   ├── DDL_bronze.sql
│   │   ├── load_bronze_enrichment.sql    # BULK INSERT stored procedure
│   │   └── load_bronze_core.py          # Python loader for core tables
│   │
│   ├── Silver/
│   │   ├── DDL_silver.sql
│   │   └── silver_load.sql              # silver.load_silver stored procedure
│   │
│   └── Gold/
│       ├── 1__ddl_gold.sql              # Dimension views + fact table DDL
│       ├── 2__load_gold_fact.sql        # gold.load_fact_orders MERGE procedure
│       └── 3__gold_indexes.sql          # 13 performance indexes
│
├── Docs/
│   ├── Olist DWP Architecture.drawio
│   ├── olist_data_flow.drawio
│   ├── olist_star_schema.drawio
│   ├── naming_conventions.md
│   └── data_catalog.md
│
├── Python/
│   ├── download_weather.py              # Open-Meteo API downloader
│   └── fix_population_encoding.py       # UTF-8 BOM fix for IBGE CSV
│
└── README.md
```

---

## Medallion Layer Design

### Bronze Layer

**Purpose:** Exact replica of source data. No transformations, no business logic.

**Loading strategy (hybrid):**

The 9 core Olist CSVs use RFC 4180 quoted fields with embedded commas — for example, city names like `"sao paulo, sp"`. SQL Server's `BULK INSERT` cannot parse these reliably with a simple field terminator. These tables are therefore loaded via Python (`pyodbc` + `pandas`) which handles quoted fields natively.

The 5 enrichment tables are clean, unquoted CSVs and are loaded via `BULK INSERT` inside the `bronze.load_bronze` stored procedure.

**Notable DDL decisions:**
- Problematic columns (dates in non-standard formats, population with comma-formatted numbers) are stored as `NVARCHAR` in Bronze. Type casting is deferred to Silver, which is the correct place for it.
- Column misspellings from the source (`product_name_lenght`) are preserved intentionally in Bronze and corrected in Silver. This documents the source defect rather than silently hiding it.

**Run order:**
```
1. python load_bronze_core.py          -- loads 9 core tables
2. EXEC bronze.load_bronze             -- loads 5 enrichment tables
```

---

### Silver Layer

**Purpose:** Cleaned, typed, and standardised data. Business logic for derived metrics lives here.

**What happens in Silver:**
- String dates cast to `DATETIME2`; population strings (`"22,728"`) stripped of commas and cast to `INT`
- Empty strings converted to `NULL`; `is_duplicate_review_id` flag set for orders with multiple reviews
- Geolocation validation: `is_valid_coordinate BIT` flags coordinates outside Brazil's bounding box
- **Delivery metrics computed:** `delivery_delay_days`, `transit_days`, and `order_to_delivery_days` — keeping these in Silver means Gold never has to recalculate them
- **FX forward-fill:** Weekend and holiday gaps in the FRED rate series are forward-filled using the correct SQL Server pattern: `COUNT(col) OVER (ORDER BY date)` as a group key with `MAX() OVER (PARTITION BY grp)` — not a running maximum
- Category translation enrichment with an override reference table (`silver.ref_category_translations_override`) for the two categories missing from the source translation file
- City name accent normalisation for population joins (handles `á`, `é`, `í`, `ó`, `ú`, `ã`, `õ`)

**Run:**
```sql
EXEC silver.load_silver
```

---

### Gold Layer

**Purpose:** Business-ready star schema. Every object here is designed to answer a specific analytical question.

**Objects:**

| Object | Type | Rows | Description |
|---|---|---|---|
| `gold.v_dim_date` | View | 774 | Date spine with holidays, FX rates, macro indicators |
| `gold.v_dim_customer` | View | 99,441 | Customers with coordinates and city size band |
| `gold.v_dim_seller` | View | 3,095 | Sellers with coordinates and city size band |
| `gold.v_dim_product` | View | 32,951 | Products with computed volume |
| `gold.v_dim_payment_type` | View | 5 | Payment type reference |
| `gold.v_dim_weather` | View | 14,248 | Weather by city and date with derived categories |
| `gold.fact_orders` | Physical table | 112,650 | One row per order line item |

**Why a physical fact table?** Dimension views resolve quickly; the fact query joins all six of them simultaneously. Materialising the fact avoids re-executing those joins on every analytical query and keeps response times under 2 seconds at 112K rows.

**Incremental load:** `gold.load_fact_orders` uses a `MERGE` statement — rows that change in Silver are updated, new rows are inserted, deleted rows are removed. A full truncate-and-reload would reset the `IDENTITY` surrogate key on every run.

**Run:**
```sql
EXEC gold.load_fact_orders
```

---

## Star Schema

```
                    ┌─────────────────┐
                    │  v_dim_date     │
                    │  (date_key)     │
                    └────────┬────────┘
                             │
┌──────────────┐    ┌────────┴────────┐    ┌──────────────────┐
│ v_dim_seller │    │  fact_orders    │    │  v_dim_customer  │
│ (seller_key) ├────┤  (fact_key PK)  ├────┤  (customer_key)  │
└──────────────┘    │                 │    └──────────────────┘
                    │  line_item_     │
┌──────────────┐    │  price          │    ┌──────────────────┐
│ v_dim_product├────┤  line_item_     ├────┤ v_dim_payment_   │
│ (product_key)│    │  freight        │    │ type             │
└──────────────┘    │  allocated_     │    └──────────────────┘
                    │  payment_value  │
┌──────────────┐    │  review_score   │
│ v_dim_weather├────┤  delivery_      │
│ (weather_key)│    │  delay_days     │
└──────────────┘    └─────────────────┘
```

`weather_key` is nullable — weather data covers 13 major cities only (~37% match rate on seller city + carrier dispatch date). This is by design; the remaining rows carry a NULL weather key rather than being excluded from the fact.

---

## Key Design Decisions

**1. Hybrid Bronze loading strategy**
BULK INSERT is fast and requires no external dependencies, but it cannot parse RFC 4180 quoted fields. Rather than preprocesssing all CSVs or abandoning BULK INSERT entirely, the two loading methods are split by source type. This is documented explicitly in both the Python script and the stored procedure.

**2. Delivery metrics in Silver, not Gold**
`delivery_delay_days`, `transit_days`, and `order_to_delivery_days` are computed in Silver. Gold simply selects them. This means any downstream consumer gets consistent metrics without recalculating.

**3. Allocated payment value**
Orders can have split payments across multiple methods. The fact table stores `allocated_payment_value` — each line item's proportional share of the total order payment, calculated as `(line_item_price / total_order_price) × total_payment_value`. This avoids double-counting in payment analysis.

**4. Latest review wins**
Some orders have multiple review rows in the source data. Silver flags these with `is_duplicate_review_id`. The Gold fact load uses `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY review_creation_date DESC)` to take the most recent review per order.

**5. Forward-fill pattern for FX rates**
The FRED dataset has no entries for weekends or holidays. The forward-fill uses `COUNT(brl_usd_rate) OVER (ORDER BY observation_date)` to generate a group number that only increments when a non-NULL value appears, then `MAX(brl_usd_rate) OVER (PARTITION BY grp)` to propagate the last known rate. Using `MAX() OVER (ORDER BY date)` instead would propagate the running maximum — a subtle but significant bug.

**6. NULL payment records**
Three line items in the source data have no corresponding payment records. Rather than erroring or fabricating values, `payment_type_key` and `allocated_payment_value` are nullable in the fact table. These rows are valid orders that happen to have incomplete payment data.

---

## Performance

All Gold queries tested in SSMS run under 2 seconds at 112,650 rows.

13 nonclustered indexes on `gold.fact_orders`:

| Index | Covers |
|---|---|
| `IX_fact_orders_date_key` | Date filtering |
| `IX_fact_orders_customer_key` | Customer analysis |
| `IX_fact_orders_seller_key` | Seller performance |
| `IX_fact_orders_product_key` | Product analysis |
| `IX_fact_orders_payment_type_key` | Payment analysis |
| `IX_fact_orders_weather_key` | Weather impact analysis |
| `IX_fact_orders_order_id` | Source tracing |
| `IX_fact_orders_order_status` | Delivered vs cancelled |
| `IX_fact_orders_date_customer` | Composite — date + customer |
| `IX_fact_orders_date_seller` | Composite — seller performance over time |
| `IX_fact_orders_date_product` | Composite — product sales trends |
| `IX_fact_orders_review_score` | Customer satisfaction queries |
| `IX_fact_orders_delivery_delay` | Late delivery analysis |

Silver layer has no indexes by design — Gold is the intended query layer, and SQL Server Express Edition has resource constraints that make large index creation on intermediate layers slow with no benefit.

---

## How to Run

### Prerequisites
- SQL Server 2025 Express Edition (or any SQL Server edition)
- SSMS
- Python 3.x with `pyodbc`, `pandas`, `requests`

### Step 1 — Database and schemas

Run in SSMS:
```sql
-- Creates Olist_DWP database and bronze/silver/gold schemas
Scripts/Bronze/DDL_bronze.sql
Scripts/Silver/DDL_silver.sql
Scripts/Gold/1__ddl_gold.sql
```

### Step 2 — Download enrichment data

```bash
python Python/download_weather.py           # downloads weather_consolidated.csv
python Python/fix_population_encoding.py    # fixes UTF-8 BOM on population CSV
```
Place all enrichment CSVs in `Datasets/Enrichment/`.

### Step 3 — Load Bronze

```bash
python Scripts/Bronze/load_bronze_core.py   # 9 core Olist tables
```
```sql
EXEC bronze.load_bronze                     -- 5 enrichment tables
```

### Step 4 — Load Silver

```sql
EXEC silver.load_silver
```

### Step 5 — Load Gold

```sql
EXEC gold.load_fact_orders
```

### Step 6 — Create indexes

```sql
-- Run once after first Gold load
Scripts/Gold/3__gold_indexes.sql
```

---

## What Makes This Different

Most public Olist repositories on GitHub:
- Load all 9 CSVs directly via BULK INSERT (fails silently on quoted fields)
- Build a flat sales report showing revenue by category and state
- Skip enrichment entirely, or add one source in isolation
- Compute delivery metrics in DAX or notebook code rather than in the warehouse

This project:
- Documents the RFC 4180 BULK INSERT limitation explicitly and solves it with a hybrid load strategy
- Combines five external data sources, all joinable to the fact at different granularities (daily, annual, by city)
- Computes all business metrics in SQL — the Gold layer is the single source of truth for any downstream consumer
- Uses a MERGE-based incremental load that handles updates and deletes — not just inserts
- Models real-world data gaps (missing payments, partial weather coverage) as NULLs with documented decisions rather than filters or fabrications

---

## Author

**Daniyal**  
Data Engineer  
[GitHub](https://github.com/) · [LinkedIn](https://linkedin.com/)

---

*Dataset: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — licensed under CC BY-NC-SA 4.0*
