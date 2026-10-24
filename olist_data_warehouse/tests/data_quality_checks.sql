/*
	Data quality checks across all three layers.
	Each check returns how many rows break the rule.
	error:   a pipeline bug. Any failure raises an error at the end.
	warning: a known gap in the source data. Reported but does not fail the run.
*/

USE Olist_DWP;
GO

SET NOCOUNT ON;

DECLARE @results TABLE (layer VARCHAR(10), check_name VARCHAR(100), failed_rows INT, severity VARCHAR(10) DEFAULT 'error');

-- bronze to silver: tables that should keep every row
INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'silver', 'row count matches bronze: ' + t, ABS(b - s)
FROM (VALUES
	('customers',   (SELECT COUNT(*) FROM bronze.crm_olist_customers_dataset),      (SELECT COUNT(*) FROM silver.crm_olist_customers_dataset)),
	('sellers',     (SELECT COUNT(*) FROM bronze.crm_olist_sellers_dataset),        (SELECT COUNT(*) FROM silver.crm_olist_sellers_dataset)),
	('order items', (SELECT COUNT(*) FROM bronze.erp_olist_order_items_dataset),    (SELECT COUNT(*) FROM silver.erp_olist_order_items_dataset)),
	('products',    (SELECT COUNT(*) FROM bronze.erp_olist_products_dataset),       (SELECT COUNT(*) FROM silver.erp_olist_products_dataset)),
	('orders',      (SELECT COUNT(*) FROM bronze.oms_olist_orders_dataset),         (SELECT COUNT(*) FROM silver.oms_olist_orders_dataset)),
	('reviews',     (SELECT COUNT(*) FROM bronze.oms_olist_orders_reviews_dataset), (SELECT COUNT(*) FROM silver.oms_olist_orders_reviews_dataset)),
	('payments',    (SELECT COUNT(*) FROM bronze.oms_olist_order_payments_dataset), (SELECT COUNT(*) FROM silver.oms_olist_order_payments_dataset))
) v (t, b, s);

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'silver', 'geolocation has one row per zip code', COUNT(*) - COUNT(DISTINCT geolocation_zip_code_prefix)
FROM silver.crm_olist_geolocation_dataset;

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'silver', 'orders: unique order_id', COUNT(*) - COUNT(DISTINCT order_id)
FROM silver.oms_olist_orders_dataset;

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'silver', 'FX calendar has no missing days', DATEDIFF(DAY, MIN(observation_date), MAX(observation_date)) + 1 - COUNT(*)
FROM silver.ext_dexbzus;

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'silver', 'FX rate filled after first observation', COUNT(*)
FROM silver.ext_dexbzus
WHERE brl_usd_rate IS NULL
	AND observation_date > (SELECT MIN(observation_date) FROM silver.ext_dexbzus WHERE brl_usd_rate IS NOT NULL);

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'silver', 'population parsed for every municipality', COUNT(*)
FROM silver.ext_municipal_population_est
WHERE populacao_estimada IS NULL OR populacao_estimada <= 0;

-- gold dimensions: surrogate keys are unique
INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'gold', 'unique key: ' + d, n - k
FROM (VALUES
	('v_dim_date',         (SELECT COUNT(*) FROM gold.v_dim_date),         (SELECT COUNT(DISTINCT date_key) FROM gold.v_dim_date)),
	('v_dim_customer',     (SELECT COUNT(*) FROM gold.v_dim_customer),     (SELECT COUNT(DISTINCT customer_key) FROM gold.v_dim_customer)),
	('v_dim_seller',       (SELECT COUNT(*) FROM gold.v_dim_seller),       (SELECT COUNT(DISTINCT seller_key) FROM gold.v_dim_seller)),
	('v_dim_product',      (SELECT COUNT(*) FROM gold.v_dim_product),      (SELECT COUNT(DISTINCT product_key) FROM gold.v_dim_product)),
	('v_dim_payment_type', (SELECT COUNT(*) FROM gold.v_dim_payment_type), (SELECT COUNT(DISTINCT payment_type_key) FROM gold.v_dim_payment_type)),
	('v_dim_weather',      (SELECT COUNT(*) FROM gold.v_dim_weather),      (SELECT COUNT(DISTINCT weather_key) FROM gold.v_dim_weather))
) v (d, n, k);

-- gold fact
INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'gold', 'fact has one row per order line', COUNT(*) - (SELECT COUNT(*) FROM silver.erp_olist_order_items_dataset)
FROM gold.fact_orders;

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'gold', 'fact grain is unique (order_id, order_item_id)', COUNT(*) - COUNT(DISTINCT CONCAT(order_id, '|', order_item_id))
FROM gold.fact_orders;

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'gold', 'every fact key exists in its dimension: ' + d, n
FROM (VALUES
	('date',         (SELECT COUNT(*) FROM gold.fact_orders f WHERE NOT EXISTS (SELECT 1 FROM gold.v_dim_date d WHERE d.date_key = f.date_key))),
	('customer',     (SELECT COUNT(*) FROM gold.fact_orders f WHERE NOT EXISTS (SELECT 1 FROM gold.v_dim_customer d WHERE d.customer_key = f.customer_key))),
	('seller',       (SELECT COUNT(*) FROM gold.fact_orders f WHERE NOT EXISTS (SELECT 1 FROM gold.v_dim_seller d WHERE d.seller_key = f.seller_key))),
	('product',      (SELECT COUNT(*) FROM gold.fact_orders f WHERE NOT EXISTS (SELECT 1 FROM gold.v_dim_product d WHERE d.product_key = f.product_key))),
	('payment type', (SELECT COUNT(*) FROM gold.fact_orders f WHERE NOT EXISTS (SELECT 1 FROM gold.v_dim_payment_type d WHERE d.payment_type_key = f.payment_type_key))),
	('weather',      (SELECT COUNT(*) FROM gold.fact_orders f WHERE f.weather_key IS NOT NULL AND NOT EXISTS (SELECT 1 FROM gold.v_dim_weather d WHERE d.weather_key = f.weather_key)))
) v (d, n);

-- allocated payments add back up to what each order actually paid (allowing for rounding)
INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'gold', 'allocated payments match order payments', COUNT(*)
FROM (
	SELECT order_id, SUM(allocated_payment_value) AS allocated, COUNT(*) AS lines
	FROM gold.fact_orders
	GROUP BY order_id
) f
JOIN (
	SELECT order_id, SUM(payment_value) AS paid
	FROM silver.oms_olist_order_payments_dataset
	GROUP BY order_id
) p ON p.order_id = f.order_id
WHERE ABS(f.allocated - p.paid) > 0.01 * f.lines;

INSERT INTO @results (layer, check_name, failed_rows)
SELECT 'gold', 'review score between 1 and 5', COUNT(*)
FROM gold.fact_orders
WHERE review_score NOT BETWEEN 1 AND 5;

INSERT INTO @results (layer, check_name, failed_rows, severity)
SELECT 'gold', 'delivered orders have a delivery date', COUNT(*), 'warning'
FROM gold.fact_orders
WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL;

SELECT
	layer,
	check_name,
	severity,
	failed_rows,
	CASE
		WHEN failed_rows = 0 THEN 'PASS'
		WHEN severity = 'warning' THEN 'WARN'
		ELSE 'FAIL'
	END AS result
FROM @results
ORDER BY CASE WHEN failed_rows = 0 THEN 1 ELSE 0 END, layer DESC, check_name;

DECLARE @failed INT = (SELECT COUNT(*) FROM @results WHERE failed_rows <> 0 AND severity = 'error');
IF @failed > 0
	RAISERROR('%d data quality check(s) failed', 16, 1, @failed);
ELSE
	PRINT 'All data quality checks passed';
GO
