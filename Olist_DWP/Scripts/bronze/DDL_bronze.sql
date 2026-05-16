/*
===============================================================================
-- Project      : Olist Data Warehouse
-- Layer        : Bronze
-- DDL Script   : Create Bronze Tables
-- Description  : Raw ingestion tables — no transformations
-- Author       : Daniyal
===============================================================================
Script Purpose:
    This script creates tables in the 'bronze' schema, dropping existing tables 
    if they already exist.
	  Run this script to re-define the DDL structure of 'bronze' Tables
===============================================================================
*/

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Olist_DWP')
BEGIN
    CREATE DATABASE Olist_DWP;
END;
GO

USE Olist_DWP;
GO

IF NOT EXISTS (SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'bronze')
BEGIN
    EXEC('CREATE SCHEMA bronze');
END;
GO

-- ============================================================
-- CRM TABLES
-- ============================================================

IF OBJECT_ID('bronze.crm_olist_customers_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.crm_olist_customers_dataset;
GO

CREATE TABLE bronze.crm_olist_customers_dataset (
    customer_id                CHAR(32),
    customer_unique_id         CHAR(32),
    customer_zip_code_prefix   NVARCHAR(10),
    customer_city              NVARCHAR(50),
    customer_state             NVARCHAR(10)
);
GO

IF OBJECT_ID('bronze.crm_olist_geolocation_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.crm_olist_geolocation_dataset;
GO

CREATE TABLE bronze.crm_olist_geolocation_dataset (
    geolocation_zip_code_prefix NVARCHAR(10),
    geolocation_lat             DECIMAL(9,6),
    geolocation_lng             DECIMAL(9,6),
    geolocation_city            NVARCHAR(50),
    geolocation_state           NVARCHAR(100)
);
GO

IF OBJECT_ID('bronze.crm_olist_sellers_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.crm_olist_sellers_dataset;
GO

CREATE TABLE bronze.crm_olist_sellers_dataset (
    seller_id                  CHAR(32),
    seller_zip_code_prefix     NVARCHAR(10),
    seller_city                NVARCHAR(50),
    seller_state               NVARCHAR(10)
);
GO

-- ============================================================
-- ERP TABLES
-- ============================================================

IF OBJECT_ID('bronze.erp_olist_order_items_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.erp_olist_order_items_dataset;
GO

CREATE TABLE bronze.erp_olist_order_items_dataset (
    order_id             CHAR(32),
    order_item_id        INT,
    product_id           CHAR(32),
    seller_id            CHAR(32),
    shipping_limit_date  DATETIME2,
    price                DECIMAL(10,2),
    freight_value        DECIMAL(10,2)
);
GO

IF OBJECT_ID('bronze.erp_olist_products_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.erp_olist_products_dataset;
GO

-- Note: product_name_lenght and product_description_lenght are misspelled
-- intentionally to match source CSV. Corrected in silver.
CREATE TABLE bronze.erp_olist_products_dataset (
    product_id                   CHAR(32),
    product_category_name        NVARCHAR(100),
    product_name_lenght          INT,
    product_description_lenght   INT,
    product_photos_qty           INT,
    product_weight_g             INT,
    product_length_cm            INT,
    product_height_cm            INT,
    product_width_cm             INT
);
GO

IF OBJECT_ID('bronze.erp_product_category_name_translation', 'U') IS NOT NULL
    DROP TABLE bronze.erp_product_category_name_translation;
GO

CREATE TABLE bronze.erp_product_category_name_translation (
    product_category_name         NVARCHAR(100),
    product_category_name_english NVARCHAR(100)
);
GO

-- ============================================================
-- OMS TABLES
-- ============================================================

IF OBJECT_ID('bronze.oms_olist_orders_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.oms_olist_orders_dataset;
GO

-- Note: All timestamp columns except order_purchase_timestamp
-- can be NULL for cancelled or incomplete orders.
CREATE TABLE bronze.oms_olist_orders_dataset (
    order_id                        CHAR(32),
    customer_id                     CHAR(32),
    order_status                    VARCHAR(32),
    order_purchase_timestamp        DATETIME2,
    order_approved_at               DATETIME2,
    order_delivered_carrier_date    DATETIME2,
    order_delivered_customer_date   DATETIME2,
    order_estimated_delivery_date   DATETIME2
);
GO

IF OBJECT_ID('bronze.oms_olist_orders_reviews_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.oms_olist_orders_reviews_dataset;
GO

-- Note: review_comment_title and review_comment_message are
-- frequently empty in source — converted to NULL in silver.

CREATE TABLE bronze.oms_olist_orders_reviews_dataset (
    review_id                 CHAR(32),
    order_id                  CHAR(32),
    review_score              INT,
    review_comment_title      NVARCHAR(100),
    review_comment_message    NVARCHAR(500),
    review_creation_date      DATETIME2,
    review_answer_timestamp   DATETIME2
);
GO

IF OBJECT_ID('bronze.oms_olist_order_payments_dataset', 'U') IS NOT NULL
    DROP TABLE bronze.oms_olist_order_payments_dataset;
GO

-- Note: One order can have multiple rows if customer used
-- split payment. Aggregated in silver.

CREATE TABLE bronze.oms_olist_order_payments_dataset (
    order_id                CHAR(32),
    payment_sequential      INT,
    payment_type            VARCHAR(20),
    payment_installments    INT,
    payment_value           DECIMAL(10,2)
);
GO

-- ============================================================
-- ENRICHMENT TABLES
-- ============================================================


IF OBJECT_ID('bronze.ext_brazil_holidays', 'U') IS NOT NULL
    DROP TABLE bronze.ext_brazil_holidays;
GO


CREATE TABLE bronze.ext_brazil_holidays(

    date            NVARCHAR(20),
    localName       NVARCHAR(200),    -- encoding to be fixed in silver
    name            NVARCHAR(200),
    countryCode     CHAR(2),
    fixed           NVARCHAR(5),    -- TRUE/FALSE string from CSV
    global          NVARCHAR(5),      -- TRUE/FALSE string from CSV
    counties        NVARCHAR(200),
    launchYear      NVARCHAR(20),
    types_0         NVARCHAR(50),
    types_1         NVARCHAR(50),
    counties_0      NVARCHAR(200)

);

GO


IF OBJECT_ID('bronze.ext_dexbzus', 'U') IS NOT NULL
    DROP TABLE bronze.ext_dexbzus;
GO


CREATE TABLE bronze.ext_dexbzus(
    observation_date    DATE,
    DEXBZUS             DECIMAL(10,4)

);

GO


IF OBJECT_ID('bronze.ext_macro_factors', 'U') IS NOT NULL
    DROP TABLE bronze.ext_macro_factors;
GO


CREATE TABLE bronze.ext_macro_factors(
    year                INT,
    gdp_usd             DECIMAL(20,2),
    inflation_pct       DECIMAL(10,6),
    unemployment_pct    DECIMAL(10,6),
    gdp_capita_usd      DECIMAL(15,6)

);

GO


IF OBJECT_ID('bronze.ext_muncipal_population_est', 'U') IS NOT NULL
    DROP TABLE bronze.ext_muncipal_population_est;
GO


CREATE TABLE bronze.ext_muncipal_population_est(

    uf                  CHAR(2),
    cod_uf              INT,
    cod_munic           NVARCHAR(10),
    nome_municipio      NVARCHAR(100),     -- city name in Portuguese — accents normalised in silver
    populacao_estimada  VARCHAR(20)       -- stored as string in bronze — commas removed and cast to INT in silver e.g. 22,728 → 22728
)

GO


IF OBJECT_ID('bronze.ext_weather_consolidated', 'U') IS NOT NULL
    DROP TABLE bronze.ext_weather_consolidated;
GO


CREATE TABLE bronze.ext_weather_consolidated(
    city_name           NVARCHAR(100),
    weather_date        DATE,
    temp_max_c          DECIMAL(5,2),
    temp_min_c          DECIMAL(5,2),
    precipitation_mm    DECIMAL(5,2),
    windspeed_max_kmh   DECIMAL(5,2)

);