-- ============================================================================
-- Gold Layer DDL: Star Schema Views
-- ============================================================================
-- Database: Olist_DWP
-- Layer: Gold
-- Purpose: Business-ready dimensional model for analytics and reporting
-- Grain: Fact table at order line item level
-- Objects: 6 views (5 dimensions views + 1 fact table)
-- ============================================================================

USE Olist_DWP;
GO

-- ============================================================================
-- DIMENSION: Date
-- ============================================================================
-- Date spine enriched with holidays, FX rates, and macro indicators
-- Covers order date range: 2016-09-04 to 2018-10-17

CREATE OR ALTER VIEW gold.v_dim_date
AS
WITH date_spine AS (
    SELECT TOP 1000
        ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS day_offset
    FROM sys.all_objects a
    CROSS JOIN sys.all_objects b
),
date_range AS (
    SELECT 
        MIN(CAST(order_purchase_timestamp AS DATE)) AS min_date,
        MAX(CAST(order_purchase_timestamp AS DATE)) AS max_date
    FROM silver.oms_olist_orders_dataset
),
dates AS (
    SELECT 
        DATEADD(DAY, ds.day_offset, dr.min_date) AS full_date
    FROM date_spine ds
    CROSS JOIN date_range dr
    WHERE DATEADD(DAY, ds.day_offset, dr.min_date) <= dr.max_date
)
SELECT
    ROW_NUMBER() OVER (ORDER BY d.full_date) AS date_key,
    d.full_date,
    YEAR(d.full_date) AS year,
    MONTH(d.full_date) AS month,
    DAY(d.full_date) AS day,
    DATENAME(MONTH, d.full_date) AS month_name,
    DATENAME(WEEKDAY, d.full_date) AS day_name,
    DATEPART(QUARTER, d.full_date) AS quarter,
    DATEPART(WEEK, d.full_date) AS week_number,
    CASE WHEN DATEPART(WEEKDAY, d.full_date) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend,
    CASE WHEN h.holiday_date IS NOT NULL THEN 1 ELSE 0 END AS is_holiday,
    h.local_name AS holiday_name,
    fx.brl_usd_rate,
    fx.is_forward_filled AS is_fx_forward_filled,
    m.gdp_usd,
    m.inflation_pct,
    m.unemployment_pct,
    m.gdp_capita_usd
FROM dates d
LEFT JOIN silver.ext_brazil_holidays h
    ON d.full_date = h.holiday_date
LEFT JOIN silver.ext_dexbzus fx
    ON d.full_date = fx.observation_date
LEFT JOIN silver.ext_macro_factors m
    ON YEAR(d.full_date) = m.year;
GO


-- ============================================================================
-- DIMENSION: Customer
-- ============================================================================
-- Customer dimension enriched with geolocation and population data

CREATE OR ALTER VIEW gold.v_dim_customer
AS
SELECT
    ROW_NUMBER() OVER (ORDER BY c.customer_id) AS customer_key,
    c.customer_id,
    c.customer_unique_id,
    c.customer_zip_code_prefix,
    c.customer_city,
    c.customer_state,
    g.geolocation_lat AS customer_lat,
    g.geolocation_lng AS customer_lng,
    g.is_valid_coordinate,
    p.populacao_estimada AS city_population,
    CASE
        WHEN p.populacao_estimada >= 1000000 THEN 'Metro'     
        WHEN p.populacao_estimada >= 100000 THEN 'Large'   
        WHEN p.populacao_estimada >= 10000 THEN 'Medium'    
        WHEN p.populacao_estimada < 10000 THEN 'Small'       
        ELSE 'Unknown'
    END AS city_size_band
FROM silver.crm_olist_customers_dataset c
LEFT JOIN silver.crm_olist_geolocation_dataset g
    ON c.customer_zip_code_prefix = g.geolocation_zip_code_prefix
LEFT JOIN silver.ext_muncipal_population_est p
    ON UPPER(c.customer_state) = p.uf
    AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        LOWER(c.customer_city), 
        'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o')
    = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        LOWER(p.nome_municipio), 
        'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o');
GO

-- ============================================================================
-- DIMENSION: Seller
-- ============================================================================
-- Seller dimension enriched with geolocation and population data

CREATE OR ALTER VIEW gold.v_dim_seller
AS
SELECT
    ROW_NUMBER() OVER (ORDER BY s.seller_id) AS seller_key,
    s.seller_id,
    s.seller_zip_code_prefix,
    s.seller_city,
    s.seller_state,
    g.geolocation_lat AS seller_lat, 
    g.geolocation_lng AS seller_lng,  
    g.is_valid_coordinate,
    p.populacao_estimada AS city_population,
    CASE
        WHEN p.populacao_estimada >= 1000000 THEN 'Metro'
        WHEN p.populacao_estimada >= 100000 THEN 'Large'
        WHEN p.populacao_estimada >= 10000 THEN 'Medium'
        WHEN p.populacao_estimada < 10000 THEN 'Small'
        ELSE 'Unknown'
    END AS city_size_band
FROM silver.crm_olist_sellers_dataset s
LEFT JOIN silver.crm_olist_geolocation_dataset g
    ON s.seller_zip_code_prefix = g.geolocation_zip_code_prefix
LEFT JOIN silver.ext_muncipal_population_est p
    ON UPPER(s.seller_state) = p.uf
    AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        LOWER(s.seller_city), 
        'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o')
    = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        LOWER(p.nome_municipio), 
        'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o');
GO


-- ============================================================================
-- DIMENSION: Product
-- ============================================================================
-- Product dimension with computed volume

CREATE OR ALTER VIEW gold.v_dim_product
AS
SELECT
    ROW_NUMBER() OVER (ORDER BY p.product_id) AS product_key,
    p.product_id,
    p.product_category_name,
    p.product_category_name_english,
    p.product_name_length,
    p.product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    CASE
        WHEN p.product_length_cm > 0 
         AND p.product_height_cm > 0 
         AND p.product_width_cm > 0
        THEN p.product_length_cm * p.product_height_cm * p.product_width_cm
        ELSE NULL
    END AS volume_cm3
FROM silver.erp_olist_products_dataset p;
GO


-- ============================================================================
-- DIMENSION: Payment Type
-- ============================================================================
-- Payment type reference dimension

CREATE OR ALTER VIEW gold.v_dim_payment_type
AS
SELECT
    ROW_NUMBER() OVER (ORDER BY payment_type) AS payment_type_key,
    payment_type,
    CASE 
        WHEN payment_type = 'credit_card' THEN 'Credit Card'
        WHEN payment_type = 'boleto' THEN 'Boleto'
        WHEN payment_type = 'voucher' THEN 'Voucher'
        WHEN payment_type = 'debit_card' THEN 'Debit Card'
        WHEN payment_type = 'not_defined' THEN 'Not Defined'
        ELSE payment_type
    END AS payment_type_display,
    CASE 
        WHEN payment_type = 'not_defined' THEN 0
        ELSE 1
    END AS is_valid_payment_type
FROM (
    SELECT DISTINCT payment_type
    FROM silver.oms_olist_order_payments_dataset
) AS distinct_types;
GO


-- ============================================================================
-- DIMENSION: Weather
-- ============================================================================
-- Weather data by city and date with derived categories

CREATE OR ALTER VIEW gold.v_dim_weather
AS
SELECT
    ROW_NUMBER() OVER (ORDER BY w.city_name, w.weather_date) AS weather_key,
    w.city_name,
    w.weather_date,
    w.temp_max_c,
    w.temp_min_c,
    w.precipitation_mm,
    w.windspeed_max_kmh,
    CASE
        WHEN w.temp_max_c IS NOT NULL THEN (w.temp_max_c + w.temp_min_c) / 2.0
        ELSE NULL
    END AS temp_avg_c,
    CASE
        WHEN w.precipitation_mm > 10 THEN 'Heavy Rain'
        WHEN w.precipitation_mm > 1 THEN 'Light Rain'
        WHEN w.precipitation_mm > 0 THEN 'Drizzle'
        ELSE 'No Rain'
    END AS precipitation_category,
    CASE
        WHEN w.temp_max_c >= 30 THEN 'Hot'
        WHEN w.temp_max_c >= 20 THEN 'Warm'
        WHEN w.temp_max_c >= 10 THEN 'Cool'
        ELSE 'Cold'
    END AS temp_category
FROM silver.ext_weather_consolidated w;
GO


-- ============================================================================
-- FACT TABLE: Orders
-- Gold Layer: Create Physical Fact Table
-- Central fact table at order line item grain
-- ============================================================================
-- Create the physical fact table

IF OBJECT_ID('gold.fact_orders', 'U') IS NOT NULL
    DROP TABLE gold.fact_orders;
GO

CREATE TABLE gold.fact_orders (
    fact_key INT IDENTITY(1,1) PRIMARY KEY,
    order_id CHAR(32) NOT NULL,
    order_item_id INT NOT NULL,
    date_key INT NOT NULL,
    customer_key INT NOT NULL,
    seller_key INT NOT NULL,
    product_key INT NOT NULL,
    payment_type_key INT NOT NULL,
    weather_key INT NULL,
    line_item_price DECIMAL(10,2) NOT NULL,
    line_item_freight DECIMAL(10,2) NOT NULL,
    allocated_payment_value DECIMAL(10,2) NOT NULL,
    review_score TINYINT NULL,
    order_status NVARCHAR(20) NOT NULL,
    delivery_delay_days INT NULL,
    transit_days INT NULL,
    order_to_delivery_days INT NULL,
    order_purchase_timestamp DATETIME2 NOT NULL,
    order_approved_at DATETIME2 NULL,
    order_delivered_carrier_date DATETIME2 NULL,
    order_delivered_customer_date DATETIME2 NULL,
    order_estimated_delivery_date DATETIME2 NULL
);
GO
-- ============================================================================
-- End of Gold Layer DDL
-- ============================================================================