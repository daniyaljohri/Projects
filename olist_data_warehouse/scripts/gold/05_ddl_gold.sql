/*
	Gold layer: star schema at order line item grain.
	Dimensions are views over silver; the fact is a physical table loaded by gold.load_fact_orders.
	Dropping and recreating gold.fact_orders clears it.
*/

USE Olist_DWP;
GO

-- calendar for the order date range, with holidays, FX rate and macro indicators
CREATE OR ALTER VIEW gold.v_dim_date
AS
WITH numbers AS (
	SELECT TOP 1000 ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS n
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
	SELECT DATEADD(DAY, n.n, r.min_date) AS full_date
	FROM numbers n
	CROSS JOIN date_range r
	WHERE DATEADD(DAY, n.n, r.min_date) <= r.max_date
)
SELECT
	ROW_NUMBER() OVER (ORDER BY d.full_date)                               AS date_key,
	d.full_date,
	YEAR(d.full_date)                                                      AS year,
	MONTH(d.full_date)                                                     AS month,
	DAY(d.full_date)                                                       AS day,
	DATENAME(MONTH, d.full_date)                                           AS month_name,
	DATENAME(WEEKDAY, d.full_date)                                         AS day_name,
	DATEPART(QUARTER, d.full_date)                                         AS quarter,
	DATEPART(WEEK, d.full_date)                                            AS week_number,
	CASE WHEN DATEPART(WEEKDAY, d.full_date) IN (1, 7) THEN 1 ELSE 0 END   AS is_weekend,
	CASE WHEN h.holiday_date IS NOT NULL THEN 1 ELSE 0 END                 AS is_holiday,
	h.local_name                                                           AS holiday_name,
	fx.brl_usd_rate,
	fx.is_forward_filled                                                   AS is_fx_forward_filled,
	m.gdp_usd,
	m.inflation_pct,
	m.unemployment_pct,
	m.gdp_capita_usd
FROM dates d
LEFT JOIN silver.ext_brazil_holidays h ON h.holiday_date = d.full_date
LEFT JOIN silver.ext_dexbzus fx ON fx.observation_date = d.full_date
LEFT JOIN silver.ext_macro_factors m ON m.year = YEAR(d.full_date);
GO

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
		WHEN p.populacao_estimada >= 100000  THEN 'Large'
		WHEN p.populacao_estimada >= 10000   THEN 'Medium'
		WHEN p.populacao_estimada <  10000   THEN 'Small'
		ELSE 'Unknown'
	END AS city_size_band
FROM silver.crm_olist_customers_dataset c
LEFT JOIN silver.crm_olist_geolocation_dataset g ON g.geolocation_zip_code_prefix = c.customer_zip_code_prefix
LEFT JOIN silver.ext_municipal_population_est p
	ON p.uf = c.customer_state
	AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(c.customer_city),
		'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o')
	  = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(p.nome_municipio),
		'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o');
GO

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
		WHEN p.populacao_estimada >= 100000  THEN 'Large'
		WHEN p.populacao_estimada >= 10000   THEN 'Medium'
		WHEN p.populacao_estimada <  10000   THEN 'Small'
		ELSE 'Unknown'
	END AS city_size_band
FROM silver.crm_olist_sellers_dataset s
LEFT JOIN silver.crm_olist_geolocation_dataset g ON g.geolocation_zip_code_prefix = s.seller_zip_code_prefix
LEFT JOIN silver.ext_municipal_population_est p
	ON p.uf = s.seller_state
	AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(s.seller_city),
		'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o')
	  = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(p.nome_municipio),
		'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o');
GO

CREATE OR ALTER VIEW gold.v_dim_product
AS
SELECT
	ROW_NUMBER() OVER (ORDER BY product_id) AS product_key,
	product_id,
	product_category_name,
	product_category_name_english,
	product_name_length,
	product_description_length,
	product_photos_qty,
	product_weight_g,
	product_length_cm,
	product_height_cm,
	product_width_cm,
	CASE
		WHEN product_length_cm > 0 AND product_height_cm > 0 AND product_width_cm > 0
		THEN product_length_cm * product_height_cm * product_width_cm
	END AS volume_cm3
FROM silver.erp_olist_products_dataset;
GO

CREATE OR ALTER VIEW gold.v_dim_payment_type
AS
SELECT
	ROW_NUMBER() OVER (ORDER BY payment_type) AS payment_type_key,
	payment_type,
	CASE payment_type
		WHEN 'credit_card' THEN 'Credit Card'
		WHEN 'boleto'      THEN 'Boleto'
		WHEN 'voucher'     THEN 'Voucher'
		WHEN 'debit_card'  THEN 'Debit Card'
		WHEN 'not_defined' THEN 'Not Defined'
		ELSE payment_type
	END AS payment_type_display,
	CASE WHEN payment_type = 'not_defined' THEN 0 ELSE 1 END AS is_valid_payment_type
FROM (SELECT DISTINCT payment_type FROM silver.oms_olist_order_payments_dataset) t

UNION ALL

-- orders with no payment record
SELECT -1, 'unknown', 'Unknown', 0;
GO

CREATE OR ALTER VIEW gold.v_dim_weather
AS
SELECT
	ROW_NUMBER() OVER (ORDER BY city_name, weather_date) AS weather_key,
	city_name,
	weather_date,
	temp_max_c,
	temp_min_c,
	precipitation_mm,
	windspeed_max_kmh,
	(temp_max_c + temp_min_c) / 2.0 AS temp_avg_c,
	CASE
		WHEN precipitation_mm > 10 THEN 'Heavy Rain'
		WHEN precipitation_mm > 1  THEN 'Light Rain'
		WHEN precipitation_mm > 0  THEN 'Drizzle'
		ELSE 'No Rain'
	END AS precipitation_category,
	CASE
		WHEN temp_max_c >= 30 THEN 'Hot'
		WHEN temp_max_c >= 20 THEN 'Warm'
		WHEN temp_max_c >= 10 THEN 'Cool'
		ELSE 'Cold'
	END AS temp_category
FROM silver.ext_weather_consolidated;
GO

DROP TABLE IF EXISTS gold.fact_orders;
CREATE TABLE gold.fact_orders (
	fact_key                        INT IDENTITY(1,1) PRIMARY KEY,
	order_id                        CHAR(32)        NOT NULL,
	order_item_id                   INT             NOT NULL,
	date_key                        INT             NOT NULL,
	customer_key                    INT             NOT NULL,
	seller_key                      INT             NOT NULL,
	product_key                     INT             NOT NULL,
	payment_type_key                INT             NOT NULL,
	weather_key                     INT,
	line_item_price                 DECIMAL(10,2)   NOT NULL,
	line_item_freight               DECIMAL(10,2)   NOT NULL,
	allocated_payment_value         DECIMAL(10,2)   NOT NULL,
	review_score                    TINYINT,
	order_status                    NVARCHAR(20)    NOT NULL,
	delivery_delay_days             INT,
	transit_days                    INT,
	order_to_delivery_days          INT,
	order_purchase_timestamp        DATETIME2       NOT NULL,
	order_approved_at               DATETIME2,
	order_delivered_carrier_date    DATETIME2,
	order_delivered_customer_date   DATETIME2,
	order_estimated_delivery_date   DATETIME2
);
GO
