# Data Catalog — Olist Data Warehouse

## Overview
The Gold Layer is the business-level data representation structured to support analytical
and reporting use cases in Power BI. It consists of dimension views and a physical fact
table built on top of the silver layer. Dimension objects are views prefixed with `v_`.
The fact table is a physical table for optimal query performance.

---

## Dimension Views

### 1. gold.v_dim_customer
**Purpose:** Customer dimension enriched with geolocation coordinates, city population,
and city size classification derived from IBGE municipal population estimates.

| Column Name             | Data Type     | Description                                                                    |
|-------------------------|---------------|--------------------------------------------------------------------------------|
| customer_key            | INT           | Surrogate key generated via ROW_NUMBER() — uniquely identifies each customer   |
| customer_id             | CHAR(32)      | MD5 hashed customer identifier — unique per order transaction                  |
| customer_unique_id      | CHAR(32)      | MD5 hashed true unique customer identifier across all orders                   |
| customer_zip_code_prefix| NVARCHAR(10)  | 5-digit Brazilian CEP postal code — stored as string to preserve leading zeros |
| customer_city           | NVARCHAR(100) | Normalised city name — lowercased, whitespace trimmed                          |
| customer_state          | CHAR(2)       | 2-letter Brazilian state code e.g. SP, RJ, MG                                  |
| customer_lat            | DECIMAL(9,6)  | Latitude coordinate from geolocation — joined on zip code                      |
| customer_lng            | DECIMAL(9,6)  | Longitude coordinate from geolocation — joined on zip code                     |
| is_valid_coordinate     | BIT           | 1 = coordinate within Brazil bounds, 0 = out of bounds                         |
| city_population         | INT           | Estimated municipal population from IBGE — 98.5% match rate                    |
| city_size_band          | NVARCHAR(10)  | Metro ≥1M, Large ≥100K, Medium ≥10K, Small <10K                                |

---

### 2. gold.v_dim_seller
**Purpose:** Seller dimension enriched with geolocation coordinates and city population.

| Column Name             | Data Type     | Description                                                                |
|-------------------------|---------------|----------------------------------------------------------------------------|
| seller_key              | INT           | Surrogate key generated via ROW_NUMBER()                                   |
| seller_id               | CHAR(32)      | MD5 hashed seller identifier                                               |
| seller_zip_code_prefix  | NVARCHAR(10)  | 5-digit Brazilian CEP postal code                                          |
| seller_city             | NVARCHAR(100) | Normalised city name — lowercased, whitespace trimmed                      |
| seller_state            | CHAR(2)       | 2-letter Brazilian state code                                              |
| seller_lat              | DECIMAL(9,6)  | Latitude coordinate from geolocation — joined on zip code                  |
| seller_lng              | DECIMAL(9,6)  | Longitude coordinate from geolocation — joined on zip code                 |
| is_valid_coordinate     | BIT           | 1 = coordinate within Brazil bounds, 0 = out of bounds                     |
| city_population         | INT           | Estimated municipal population from IBGE                                   |
| city_size_band          | NVARCHAR(10)  | Metro ≥1M, Large ≥100K, Medium ≥10K, Small <10K                            |

---

### 3. gold.v_dim_product
**Purpose:** Product dimension with English category names and computed physical attributes.

| Column Name                   | Data Type     | Description                                                                |
|-------------------------------|---------------|----------------------------------------------------------------------------|
| product_key                   | INT           | Surrogate key generated via ROW_NUMBER()                                   |
| product_id                    | CHAR(32)      | MD5 hashed product identifier                                              |
| product_category_name         | NVARCHAR(100) | Original Portuguese category name from source                              |
| product_category_name_english | NVARCHAR(100) | English translation — joined from translation table, defaults to 'unknown' |
| product_name_length           | INT           | Character count of product name                                            |
| product_description_length    | INT           | Character count of product description                                     |
| product_photos_qty            | INT           | Number of product photos listed                                            |
| product_weight_g              | INT           | Product weight in grams                                                    |
| product_length_cm             | INT           | Product length in centimetres                                              |
| product_height_cm             | INT           | Product height in centimetres                                              |
| product_width_cm              | INT           | Product width in centimetres                                               |
| product_volume_cm3            | INT           | Computed volume — length × height × width                                  |

---

### 4. gold.v_dim_date
**Purpose:** Date dimension covering full order date range dynamically. Enriched with
public holiday flags, BRL/USD exchange rates, and annual macro economic indicators.

| Column Name          | Data Type     | Description                                                                   |
|----------------------|---------------|-------------------------------------------------------------------------------|
| date_key             | INT           | Surrogate key generated via ROW_NUMBER()                                      |
| full_date            | DATE          | Calendar date                                                                 |
| year                 | INT           | Calendar year e.g. 2016                                                       |
| month                | INT           | Month number 1–12                                                             |
| day                  | INT           | Day of month 1–31                                                             |
| month_name           | NVARCHAR(20)  | Full month name e.g. January                                                  |
| day_name             | NVARCHAR(20)  | Full day name e.g. Monday                                                     |
| quarter              | INT           | Quarter number 1–4                                                            |
| week_number          | INT           | ISO week number                                                               |
| is_weekend           | BIT           | 1 = Saturday or Sunday, 0 = weekday                                           |
| is_holiday           | BIT           | 1 = Brazilian public holiday, 0 = regular day                                 |
| holiday_name         | NVARCHAR(200) | Name of the public holiday if applicable, NULL otherwise                      |
| brl_usd_rate         | DECIMAL(10,4) | BRL per 1 USD — forward filled for weekends and holidays from FRED DEXBZUS    |
| is_fx_forward_filled | BIT           | 1 = rate was forward filled, 0 = actual observed market rate                  |
| gdp_usd              | DECIMAL(20,2) | Brazil annual GDP in USD from World Bank — joined on year                     |
| inflation_pct        | DECIMAL(10,6) | Brazil annual inflation % from World Bank — joined on year                    |
| unemployment_pct     | DECIMAL(10,6) | Brazil annual unemployment % from World Bank — joined on year                 |
| gdp_capita_usd       | DECIMAL(15,6) | Brazil GDP per capita in USD from World Bank — joined on year                 |

---

### 5. gold.v_dim_weather
**Purpose:** Weather dimension covering 13 major Brazilian cities across 2016–2018.
Joins to fact on seller city and carrier dispatch date.

| Column Name        | Data Type     | Description                                                                      |
|--------------------|---------------|----------------------------------------------------------------------------------|
| weather_key        | INT           | Surrogate key generated via ROW_NUMBER()                                         |
| city_name          | NVARCHAR(100) | City name — lowercase, no accents, matches seller_city in dim_seller             |
| weather_date       | DATE          | Calendar date of weather observation                                             |
| temp_max_c         | DECIMAL(5,2)  | Maximum temperature in Celsius                                                   |
| temp_min_c         | DECIMAL(5,2)  | Minimum temperature in Celsius                                                   |
| precipitation_mm   | DECIMAL(6,2)  | Total precipitation in millimetres                                               |
| windspeed_max_kmh  | DECIMAL(6,2)  | Maximum wind speed in km/h                                                       |

---

### 6. gold.v_dim_payment_type
**Purpose:** Payment type attribute derived from olist payments table for simple lookup in analysis.
Joins to fact on payment type key.

| Column Name           | Data Type     | Description                                                                      |
|-----------------------|---------------|----------------------------------------------------------------------------------|
| payment_type_key      | INT           | Surrogate key generated via ROW_NUMBER()                                         |
| payment_type          | VARCHAR(20)   | Payment type — lowercase, no accents, from olist payments table                  |
| payment_type_display  | VARCHAR(20)   | Payment type formatted for business use and reporting                            |
| is_valid_payment_type | INT           | payment type validity flag                                                       |

---
## Fact Table

### 7. gold.fact_orders
**Purpose:** Central fact table at order line item grain. One row per order line item.
Order-level metrics repeat across line items and should use AVERAGE or MAX in
Power BI, not SUM. Payment share is proportionally allocated per line item.

| Column Name                    | Data Type     | Description                                                                |
|--------------------------------|---------------|----------------------------------------------------------------------------|
| fact_key                       | INT           | Surrogate primary key (IDENTITY) — uniquely identifies each row            |
| order_id                       | CHAR(32)      | MD5 hashed order identifier — repeats across line items                    |
| order_item_id                  | INT           | Line item sequence number within the order                                 |
| date_key                       | INT           | FK to gold.v_dim_date — based on order purchase date                       |
| customer_key                   | INT           | FK to gold.v_dim_customer                                                  |
| seller_key                     | INT           | FK to gold.v_dim_seller                                                    |
| product_key                    | INT           | FK to gold.v_dim_product                                                   |
| payment_type_key               | INT           | FK to gold.v_dim_payment_type                                              |
| weather_key                    | INT           | FK to gold.v_dim_weather — based on carrier dispatch date and seller city  |
| line_item_price                | DECIMAL(10,2) | Line item price in BRL                                                     |
| line_item_freight              | DECIMAL(10,2) | Line item freight cost in BRL                                              |
| allocated_payment_value        | DECIMAL(10,2) | Proportional share of total order payment allocated to this line item      |
| review_score                   | TINYINT       | Customer satisfaction score 1–5 — repeats across line items                |
| order_status                   | NVARCHAR(20)  | Order lifecycle status e.g. delivered, shipped, canceled                   |
| delivery_delay_days            | INT           | Actual minus estimated delivery days — positive = late, negative = early   |
| transit_days                   | INT           | Days from carrier pickup to customer delivery                              |
| order_to_delivery_days         | INT           | Days from purchase to customer delivery                                    |
| order_purchase_timestamp       | DATETIME2     | Order purchase timestamp                                                   |
| order_approved_at              | DATETIME2     | Order approval timestamp                                                   |
| order_delivered_carrier_date   | DATETIME2     | Carrier pickup timestamp                                                   |
| order_delivered_customer_date  | DATETIME2     | Customer delivery timestamp                                                |
| order_estimated_delivery_date  | DATETIME2     | Estimated delivery date from seller                                        |