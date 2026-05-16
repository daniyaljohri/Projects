# Naming Conventions — Olist Data Warehouse

## Table of Contents
1. [General Principles](#general-principles)
2. [Table Naming Conventions](#table-naming-conventions)
3. [Column Naming Conventions](#column-naming-conventions)
4. [Stored Procedures](#stored-procedures)
5. [Python Scripts](#python-scripts)

---

## General Principles

- Use snake_case for all object names — lowercase letters and underscores only
- Use English for all names
- Avoid SQL reserved words as object names
- Source system prefixes preserved through bronze and silver layers
- Gold layer uses business-aligned names only

---

## Table Naming Conventions

### Bronze Rules
All table names must start with the source system prefix and match the original
source file name as closely as possible. No renaming or abbreviation.

**Pattern:** `<sourcesystem>_<entity>`

| Source System  | Prefix | Example                                    |
|----------------|--------|--------------------------------------------|
| CRM            | `crm_` | `crm_olist_customers_dataset`              |
| ERP            | `erp_` | `erp_olist_products_dataset`               |
| OMS            | `oms_` | `oms_olist_orders_dataset`                 |
| External       | `ext_` | `ext_weather_consolidated`                 |

### Silver Rules
Same naming pattern as bronze — source system prefix preserved. Table names
match bronze exactly. No renaming between bronze and silver.

**Pattern:** `<sourcesystem>_<entity>`

Examples:
- `crm_olist_customers_dataset`
- `erp_olist_products_dataset`
- `oms_olist_orders_dataset`
- `ext_dexbzus`

Reference tables use the `ref_` prefix:
- `ref_category_translations_override`
- `ref_city_name_override`

### Gold Rules
Dimension objects are views. Fact table is a physical table for performance.
Views are prefixed with `v_` followed by the category prefix.

**Pattern:** `v_<category>_<entity>` for dimensions, `fact_<entity>` for fact tables

| Pattern      | Meaning           | Example                  |
|--------------|-------------------|--------------------------|
| `v_dim_`     | Dimension view    | `v_dim_customer`         |
| `fact_`      | Fact table        | `fact_orders`            |

---

## Column Naming Conventions

### Surrogate Keys
All primary keys in dimension views use the suffix `_key`.

**Pattern:** `<entity>_key`

Examples:
- `customer_key` — surrogate key in `v_dim_customer`
- `seller_key` — surrogate key in `v_dim_seller`
- `product_key` — surrogate key in `v_dim_product`
- `date_key` — surrogate key in `v_dim_date`
- `weather_key` — surrogate key in `v_dim_weather`

### Foreign Keys
Fact table foreign keys match the dimension surrogate key name exactly.

Examples:
- `customer_key` in `v_fact_orders` → joins to `v_dim_customer.customer_key`
- `seller_key` in `v_fact_orders` → joins to `v_dim_seller.seller_key`

### Flag Columns
Boolean flag columns use the prefix `is_`.

Examples:
- `is_valid_coordinate` — geolocation quality flag
- `is_holiday` — public holiday flag
- `is_weekend` — weekend flag
- `is_fx_forward_filled` — FX rate forward fill flag
- `is_duplicate_review_id` — duplicate review flag
- `is_valid_payment_type` — payment type validity flag

### Technical Columns
All system-generated audit columns use the prefix `dwh_`.

**Pattern:** `dwh_<column_name>`

Examples:
- `dwh_create_date` — timestamp when the record was loaded into the layer

### Derived Columns
Columns computed from other columns are named to reflect the calculation clearly.

Examples:
- `delivery_delay_days` — actual minus estimated delivery date
- `transit_days` — carrier pickup to customer delivery
- `order_to_delivery_days` — purchase to customer delivery
- `payment_share` — proportional payment allocation per line item
- `product_volume_cm3` — length × height × width
- `city_size_band` — derived population classification

---

## Stored Procedures

All stored procedures for loading data follow this pattern:

**Pattern:** `<schema>.load_<layer>` or `<schema>.load_<entity>`

| Procedure                | Description                                        |
|--------------------------|----------------------------------------------------|
| `bronze.load_bronze`     | Loads enrichment tables via BULK INSERT            |
| `silver.load_silver`     | Truncates and reloads all silver tables from bronze|
| `gold.load_fact_orders`  | Incrementally loads fact_orders table using MERGE  |

---

## Python Scripts

| Script                        | Purpose                                                      | Run frequency  |
|-------------------------------|--------------------------------------------------------------|----------------|
| `load_bronze.py`              | Loads 9 core Olist tables into bronze via pyodbc             | Every pipeline run |
| `download_weather.py`         | Downloads weather data from Open-Meteo API                   | One-time       |
| `fix_population_encoding.py`  | Fixes encoding corruption in IBGE population CSV             | One-time       |