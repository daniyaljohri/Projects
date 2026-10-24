/*
===============================================================================
Script   : 01_ddl_bronze.sql
Layer    : Bronze
Purpose  : Creates the raw landing tables. No cleaning, no business logic.
Run      : After 00_init_database.sql.
Warning  : Drops and recreates every bronze table. Existing bronze data is lost.

Notes
- Columns that arrive in awkward formats are kept as text here and cast in
  silver (deferred typing):
    ext_dexbzus           dates are DD/MM/YYYY, missing rates are blank
    ext_brazil_holidays   dates are DD/MM/YYYY, booleans are TRUE/FALSE
    ext_municipal_...     population has thousands separators, e.g. "22,728"
- Source typos are kept on purpose (product_name_lenght) and fixed in silver,
  so bronze stays a faithful copy of the source.
===============================================================================
*/

USE Olist_DWP;
GO

-- ============================================================
-- CRM
-- ============================================================

DROP TABLE IF EXISTS bronze.crm_olist_customers_dataset;
CREATE TABLE bronze.crm_olist_customers_dataset (
	customer_id                 CHAR(32),
	customer_unique_id          CHAR(32),
	customer_zip_code_prefix    NVARCHAR(10),
	customer_city               NVARCHAR(50),
	customer_state              NVARCHAR(10)
);

DROP TABLE IF EXISTS bronze.crm_olist_geolocation_dataset;
CREATE TABLE bronze.crm_olist_geolocation_dataset (
	geolocation_zip_code_prefix NVARCHAR(10),
	geolocation_lat             DECIMAL(9,6),
	geolocation_lng             DECIMAL(9,6),
	geolocation_city            NVARCHAR(50),
	geolocation_state           NVARCHAR(100)
);

DROP TABLE IF EXISTS bronze.crm_olist_sellers_dataset;
CREATE TABLE bronze.crm_olist_sellers_dataset (
	seller_id                   CHAR(32),
	seller_zip_code_prefix      NVARCHAR(10),
	seller_city                 NVARCHAR(50),
	seller_state                NVARCHAR(10)
);

-- ============================================================
-- ERP
-- ============================================================

DROP TABLE IF EXISTS bronze.erp_olist_order_items_dataset;
CREATE TABLE bronze.erp_olist_order_items_dataset (
	order_id                    CHAR(32),
	order_item_id               INT,
	product_id                  CHAR(32),
	seller_id                   CHAR(32),
	shipping_limit_date         DATETIME2,
	price                       DECIMAL(10,2),
	freight_value               DECIMAL(10,2)
);

DROP TABLE IF EXISTS bronze.erp_olist_products_dataset;
CREATE TABLE bronze.erp_olist_products_dataset (
	product_id                  CHAR(32),
	product_category_name       NVARCHAR(100),
	product_name_lenght         INT,
	product_description_lenght  INT,
	product_photos_qty          INT,
	product_weight_g            INT,
	product_length_cm           INT,
	product_height_cm           INT,
	product_width_cm            INT
);

DROP TABLE IF EXISTS bronze.erp_product_category_name_translation;
CREATE TABLE bronze.erp_product_category_name_translation (
	product_category_name           NVARCHAR(100),
	product_category_name_english   NVARCHAR(100)
);

-- ============================================================
-- OMS
-- ============================================================

DROP TABLE IF EXISTS bronze.oms_olist_orders_dataset;
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

DROP TABLE IF EXISTS bronze.oms_olist_orders_reviews_dataset;
CREATE TABLE bronze.oms_olist_orders_reviews_dataset (
	review_id                   CHAR(32),
	order_id                    CHAR(32),
	review_score                INT,
	review_comment_title        NVARCHAR(100),
	review_comment_message      NVARCHAR(500),
	review_creation_date        DATETIME2,
	review_answer_timestamp     DATETIME2
);

DROP TABLE IF EXISTS bronze.oms_olist_order_payments_dataset;
CREATE TABLE bronze.oms_olist_order_payments_dataset (
	order_id                    CHAR(32),
	payment_sequential          INT,
	payment_type                VARCHAR(20),
	payment_installments        INT,
	payment_value               DECIMAL(10,2)
);

-- ============================================================
-- ENRICHMENT
-- ============================================================

DROP TABLE IF EXISTS bronze.ext_brazil_holidays;
CREATE TABLE bronze.ext_brazil_holidays (
	date                        NVARCHAR(20),
	localName                   NVARCHAR(200),
	name                        NVARCHAR(200),
	countryCode                 CHAR(2),
	fixed                       NVARCHAR(5),
	global                      NVARCHAR(5),
	counties                    NVARCHAR(200),
	launchYear                  NVARCHAR(20),
	types_0                     NVARCHAR(50),
	types_1                     NVARCHAR(50),
	counties_0                  NVARCHAR(200)
);

DROP TABLE IF EXISTS bronze.ext_dexbzus;
CREATE TABLE bronze.ext_dexbzus (
	observation_date            NVARCHAR(20),
	DEXBZUS                     NVARCHAR(20)
);

DROP TABLE IF EXISTS bronze.ext_macro_factors;
CREATE TABLE bronze.ext_macro_factors (
	year                        INT,
	gdp_usd                     DECIMAL(20,2),
	inflation_pct               DECIMAL(10,6),
	unemployment_pct            DECIMAL(10,6),
	gdp_capita_usd              DECIMAL(15,6)
);

DROP TABLE IF EXISTS bronze.ext_municipal_population_est;
CREATE TABLE bronze.ext_municipal_population_est (
	uf                          CHAR(2),
	cod_uf                      INT,
	cod_munic                   NVARCHAR(10),
	nome_municipio              NVARCHAR(100),
	populacao_estimada          VARCHAR(20)
);

DROP TABLE IF EXISTS bronze.ext_weather_consolidated;
CREATE TABLE bronze.ext_weather_consolidated (
	city_name                   NVARCHAR(100),
	weather_date                DATE,
	temp_max_c                  DECIMAL(5,2),
	temp_min_c                  DECIMAL(5,2),
	precipitation_mm            DECIMAL(5,2),
	windspeed_max_kmh           DECIMAL(5,2)
);
GO

SELECT t.name AS bronze_table, COUNT(c.column_id) AS column_count
FROM sys.tables t
JOIN sys.columns c ON c.object_id = t.object_id
WHERE t.schema_id = SCHEMA_ID('bronze')
GROUP BY t.name
ORDER BY t.name;
GO
