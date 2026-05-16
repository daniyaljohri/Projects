-- ============================================================
-- Project      : Olist Data Warehouse
-- Layer        : Silver
-- DDL Script   : Create Silver Tables
-- Description  : Cleaned and standardised tables
-- Author       : Daniyal
-- ============================================================

USE Olist_DWP;
GO

IF NOT EXISTS (SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'silver')
BEGIN
    EXEC('CREATE SCHEMA silver');
END;
GO

-- ============================================================
-- CRM TABLES
-- ============================================================

IF OBJECT_ID('silver.crm_olist_customers_dataset', 'U') IS NOT NULL
    DROP TABLE silver.crm_olist_customers_dataset;
GO

CREATE TABLE silver.crm_olist_customers_dataset (
    customer_id                CHAR(32)        NOT NULL,
    customer_unique_id         CHAR(32),
    customer_zip_code_prefix   NVARCHAR(10),
    customer_city              NVARCHAR(100),
    customer_state             CHAR(2),
    dwh_create_date            DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.crm_olist_geolocation_dataset', 'U') IS NOT NULL
    DROP TABLE silver.crm_olist_geolocation_dataset;
GO

CREATE TABLE silver.crm_olist_geolocation_dataset (
    geolocation_zip_code_prefix   NVARCHAR(10)    NOT NULL,
    geolocation_lat               DECIMAL(9,6),
    geolocation_lng               DECIMAL(9,6),
    geolocation_city              NVARCHAR(100),
    geolocation_state             CHAR(2),
    is_valid_coordinate           BIT             NOT NULL,
    dwh_create_date               DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.crm_olist_sellers_dataset', 'U') IS NOT NULL
    DROP TABLE silver.crm_olist_sellers_dataset;
GO

CREATE TABLE silver.crm_olist_sellers_dataset (
    seller_id                  CHAR(32)        NOT NULL,
    seller_zip_code_prefix     NVARCHAR(10),
    seller_city                NVARCHAR(100),
    seller_state               CHAR(2),
    dwh_create_date            DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

-- ============================================================
-- ERP TABLES
-- ============================================================

IF OBJECT_ID('silver.erp_olist_order_items_dataset', 'U') IS NOT NULL
    DROP TABLE silver.erp_olist_order_items_dataset;
GO

CREATE TABLE silver.erp_olist_order_items_dataset (
    order_id             CHAR(32)        NOT NULL,
    order_item_id        INT             NOT NULL,
    product_id           CHAR(32)        NOT NULL,
    seller_id            CHAR(32)        NOT NULL,
    shipping_limit_date  DATETIME2,
    price                DECIMAL(10,2),
    freight_value        DECIMAL(10,2),
    dwh_create_date      DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.erp_olist_products_dataset', 'U') IS NOT NULL
    DROP TABLE silver.erp_olist_products_dataset;
GO

CREATE TABLE silver.erp_olist_products_dataset (
    product_id                      CHAR(32)        NOT NULL,
    product_category_name           NVARCHAR(100),
    product_category_name_english   NVARCHAR(100),
    product_name_length             INT,
    product_description_length      INT,
    product_photos_qty              INT,
    product_weight_g                INT,
    product_length_cm               INT,
    product_height_cm               INT,
    product_width_cm                INT,
    dwh_create_date                 DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

-- Reference table for missing category translations
-- Add new entries here as they are discovered — no script changes needed
IF OBJECT_ID('silver.ref_category_translations_override', 'U') IS NOT NULL
    DROP TABLE silver.ref_category_translations_override;
GO

CREATE TABLE silver.ref_category_translations_override (
    product_category_name           NVARCHAR(100)   NOT NULL,
    product_category_name_english   NVARCHAR(100)   NOT NULL
);
GO

INSERT INTO silver.ref_category_translations_override VALUES
('pc_gamer',                                          'pc gamer'),
('portateis_cozinha_e_preparadores_de_alimentos',     'portable kitchen and food processors');
GO

IF OBJECT_ID('silver.erp_product_category_name_translation', 'U') IS NOT NULL
    DROP TABLE silver.erp_product_category_name_translation;
GO

CREATE TABLE silver.erp_product_category_name_translation (
    product_category_name           NVARCHAR(100)   NOT NULL,
    product_category_name_english   NVARCHAR(100)   NOT NULL,
    dwh_create_date                 DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

-- ============================================================
-- OMS TABLES
-- ============================================================

IF OBJECT_ID('silver.oms_olist_orders_dataset', 'U') IS NOT NULL
    DROP TABLE silver.oms_olist_orders_dataset;
GO

CREATE TABLE silver.oms_olist_orders_dataset (
    order_id                        CHAR(32)        NOT NULL,
    customer_id                     CHAR(32),
    order_status                    VARCHAR(20),
    order_purchase_timestamp        DATETIME2,
    order_approved_at               DATETIME2,
    order_delivered_carrier_date    DATETIME2,
    order_delivered_customer_date   DATETIME2,
    order_estimated_delivery_date   DATETIME2,
    delivery_delay_days             INT,
    transit_days                    INT,
    order_to_delivery_days          INT,
    dwh_create_date                 DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.oms_olist_orders_reviews_dataset', 'U') IS NOT NULL
    DROP TABLE silver.oms_olist_orders_reviews_dataset;
GO

CREATE TABLE silver.oms_olist_orders_reviews_dataset (
    review_id                 CHAR(32)        NOT NULL,
    order_id                  CHAR(32),
    review_score              INT,
    review_comment_title      NVARCHAR(100),
    review_comment_message    NVARCHAR(500),
    review_creation_date      DATETIME2,
    review_answer_timestamp   DATETIME2,
    is_duplicate_review_id    BIT             NOT NULL    DEFAULT 0,
    dwh_create_date           DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.oms_olist_order_payments_dataset', 'U') IS NOT NULL
    DROP TABLE silver.oms_olist_order_payments_dataset;
GO

CREATE TABLE silver.oms_olist_order_payments_dataset (
    order_id                CHAR(32)        NOT NULL,
    payment_sequential      INT,
    payment_type            VARCHAR(20),
    payment_installments    INT,
    payment_value           DECIMAL(10,2),
    is_valid_payment_type   BIT             NOT NULL    DEFAULT 1,
    dwh_create_date         DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

-- ============================================================
-- ENRICHMENT TABLES
-- ============================================================

IF OBJECT_ID('silver.ext_weather_consolidated', 'U') IS NOT NULL
    DROP TABLE silver.ext_weather_consolidated;
GO

CREATE TABLE silver.ext_weather_consolidated (
    city_name           NVARCHAR(100)   NOT NULL,
    weather_date        DATE            NOT NULL,
    temp_max_c          DECIMAL(5,2),
    temp_min_c          DECIMAL(5,2),
    precipitation_mm    DECIMAL(6,2),
    windspeed_max_kmh   DECIMAL(6,2),
    dwh_create_date     DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.ext_dexbzus', 'U') IS NOT NULL
    DROP TABLE silver.ext_dexbzus;
GO

CREATE TABLE silver.ext_dexbzus (
    observation_date    DATE            NOT NULL,
    brl_usd_rate        DECIMAL(10,4),
    is_forward_filled   BIT             NOT NULL    DEFAULT 0,
    dwh_create_date     DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.ext_macro_factors', 'U') IS NOT NULL
    DROP TABLE silver.ext_macro_factors;
GO

CREATE TABLE silver.ext_macro_factors (
    year                SMALLINT        NOT NULL,
    gdp_usd             DECIMAL(20,2),
    inflation_pct       DECIMAL(10,6),
    unemployment_pct    DECIMAL(10,6),
    gdp_capita_usd      DECIMAL(15,6),
    dwh_create_date     DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO

IF OBJECT_ID('silver.ext_muncipal_population_est', 'U') IS NOT NULL
    DROP TABLE silver.ext_muncipal_population_est;
GO

CREATE TABLE silver.ext_muncipal_population_est (
    uf                  CHAR(2)         NOT NULL,
    cod_uf              INT,
    cod_munic           NVARCHAR(10),
    nome_municipio      NVARCHAR(100),
    populacao_estimada  INT,
    dwh_create_date     DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO


IF OBJECT_ID('silver.ext_brazil_holidays', 'U') IS NOT NULL
    DROP TABLE silver.ext_brazil_holidays;
GO

CREATE TABLE silver.ext_brazil_holidays (
    holiday_date        DATE            NOT NULL,
    local_name          NVARCHAR(200),
    name                NVARCHAR(200),
    country_code        CHAR(2),
    is_fixed            BIT,
    is_global           BIT,
    holiday_type        NVARCHAR(50),
    holiday_type_2      NVARCHAR(50),
    dwh_create_date     DATETIME2       NOT NULL    DEFAULT GETDATE()
);
GO