/*
	Silver tables: cleaned and typed copies of bronze.
	Drops and recreates every silver table.
*/

USE Olist_DWP;
GO

-- CRM

DROP TABLE IF EXISTS silver.crm_olist_customers_dataset;
CREATE TABLE silver.crm_olist_customers_dataset (
	customer_id                 CHAR(32)        NOT NULL,
	customer_unique_id          CHAR(32),
	customer_zip_code_prefix    NVARCHAR(10),
	customer_city               NVARCHAR(100),
	customer_state              CHAR(2),
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.crm_olist_geolocation_dataset;
CREATE TABLE silver.crm_olist_geolocation_dataset (
	geolocation_zip_code_prefix NVARCHAR(10)    NOT NULL,
	geolocation_lat             DECIMAL(9,6),
	geolocation_lng             DECIMAL(9,6),
	geolocation_city            NVARCHAR(100),
	geolocation_state           CHAR(2),
	is_valid_coordinate         BIT             NOT NULL,
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.crm_olist_sellers_dataset;
CREATE TABLE silver.crm_olist_sellers_dataset (
	seller_id                   CHAR(32)        NOT NULL,
	seller_zip_code_prefix      NVARCHAR(10),
	seller_city                 NVARCHAR(100),
	seller_state                CHAR(2),
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

-- ERP

DROP TABLE IF EXISTS silver.erp_olist_order_items_dataset;
CREATE TABLE silver.erp_olist_order_items_dataset (
	order_id                    CHAR(32)        NOT NULL,
	order_item_id               INT             NOT NULL,
	product_id                  CHAR(32)        NOT NULL,
	seller_id                   CHAR(32)        NOT NULL,
	shipping_limit_date         DATETIME2,
	price                       DECIMAL(10,2),
	freight_value               DECIMAL(10,2),
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.erp_olist_products_dataset;
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
	dwh_create_date                 DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.erp_product_category_name_translation;
CREATE TABLE silver.erp_product_category_name_translation (
	product_category_name           NVARCHAR(100)   NOT NULL,
	product_category_name_english   NVARCHAR(100)   NOT NULL,
	dwh_create_date                 DATETIME2       NOT NULL DEFAULT GETDATE()
);

-- categories missing from the Olist translation file
DROP TABLE IF EXISTS silver.ref_category_translations_override;
CREATE TABLE silver.ref_category_translations_override (
	product_category_name           NVARCHAR(100)   NOT NULL,
	product_category_name_english   NVARCHAR(100)   NOT NULL
);

INSERT INTO silver.ref_category_translations_override VALUES
	('pc_gamer',                                      'pc gamer'),
	('portateis_cozinha_e_preparadores_de_alimentos', 'portable kitchen and food processors');

-- OMS

DROP TABLE IF EXISTS silver.oms_olist_orders_dataset;
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
	dwh_create_date                 DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.oms_olist_orders_reviews_dataset;
CREATE TABLE silver.oms_olist_orders_reviews_dataset (
	review_id                   CHAR(32)        NOT NULL,
	order_id                    CHAR(32),
	review_score                INT,
	review_comment_title        NVARCHAR(100),
	review_comment_message      NVARCHAR(500),
	review_creation_date        DATETIME2,
	review_answer_timestamp     DATETIME2,
	is_duplicate_review_id      BIT             NOT NULL DEFAULT 0,
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.oms_olist_order_payments_dataset;
CREATE TABLE silver.oms_olist_order_payments_dataset (
	order_id                    CHAR(32)        NOT NULL,
	payment_sequential          INT,
	payment_type                VARCHAR(20),
	payment_installments        INT,
	payment_value               DECIMAL(10,2),
	is_valid_payment_type       BIT             NOT NULL DEFAULT 1,
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

-- Enrichment

DROP TABLE IF EXISTS silver.ext_weather_consolidated;
CREATE TABLE silver.ext_weather_consolidated (
	city_name                   NVARCHAR(100)   NOT NULL,
	weather_date                DATE            NOT NULL,
	temp_max_c                  DECIMAL(5,2),
	temp_min_c                  DECIMAL(5,2),
	precipitation_mm            DECIMAL(6,2),
	windspeed_max_kmh           DECIMAL(6,2),
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.ext_dexbzus;
CREATE TABLE silver.ext_dexbzus (
	observation_date            DATE            NOT NULL,
	brl_usd_rate                DECIMAL(10,4),
	is_forward_filled           BIT             NOT NULL DEFAULT 0,
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.ext_macro_factors;
CREATE TABLE silver.ext_macro_factors (
	year                        SMALLINT        NOT NULL,
	gdp_usd                     DECIMAL(20,2),
	inflation_pct               DECIMAL(10,6),
	unemployment_pct            DECIMAL(10,6),
	gdp_capita_usd              DECIMAL(15,6),
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.ext_municipal_population_est;
CREATE TABLE silver.ext_municipal_population_est (
	uf                          CHAR(2)         NOT NULL,
	cod_uf                      INT,
	cod_munic                   NVARCHAR(10),
	nome_municipio              NVARCHAR(100),
	populacao_estimada          INT,
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);

DROP TABLE IF EXISTS silver.ext_brazil_holidays;
CREATE TABLE silver.ext_brazil_holidays (
	holiday_date                DATE            NOT NULL,
	local_name                  NVARCHAR(200),
	name                        NVARCHAR(200),
	country_code                CHAR(2),
	is_fixed                    BIT,
	is_global                   BIT,
	holiday_type                NVARCHAR(50),
	holiday_type_2              NVARCHAR(50),
	dwh_create_date             DATETIME2       NOT NULL DEFAULT GETDATE()
);
GO
