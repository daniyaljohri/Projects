/*
	Loads gold.fact_orders from silver and the gold dimensions.
	MERGE keeps fact_key stable across runs: changed rows are updated, new rows
	inserted and rows no longer in silver deleted.
	EXEC gold.load_fact_orders;
*/

USE Olist_DWP;
GO

CREATE OR ALTER PROCEDURE gold.load_fact_orders
AS
BEGIN
	SET NOCOUNT ON;
	SET XACT_ABORT ON;

	DECLARE @start DATETIME2 = SYSDATETIME();

	WITH order_totals AS (
		SELECT order_id, SUM(price) AS total_order_price
		FROM silver.erp_olist_order_items_dataset
		GROUP BY order_id
	),
	payment_totals AS (
		SELECT order_id, SUM(payment_value) AS total_payment_value
		FROM silver.oms_olist_order_payments_dataset
		GROUP BY order_id
	),
	-- orders can be split across payment methods; the largest one is used for the dimension
	main_payment AS (
		SELECT order_id, payment_type,
			ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY payment_value DESC) AS rn
		FROM silver.oms_olist_order_payments_dataset
	),
	latest_review AS (
		SELECT order_id, review_score,
			ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY review_creation_date DESC) AS rn
		FROM silver.oms_olist_orders_reviews_dataset
	),
	staging AS (
		SELECT
			oi.order_id,
			oi.order_item_id,
			dd.date_key,
			dc.customer_key,
			ds.seller_key,
			dp.product_key,
			COALESCE(dpt.payment_type_key, -1) AS payment_type_key,
			dw.weather_key,
			oi.price AS line_item_price,
			oi.freight_value AS line_item_freight,
			-- each line's share of what the customer actually paid for the order
			CASE
				WHEN ot.total_order_price > 0
				THEN oi.price / ot.total_order_price * ISNULL(pt.total_payment_value, 0)
				ELSE 0
			END AS allocated_payment_value,
			lr.review_score,
			o.order_status,
			o.delivery_delay_days,
			o.transit_days,
			o.order_to_delivery_days,
			o.order_purchase_timestamp,
			o.order_approved_at,
			o.order_delivered_carrier_date,
			o.order_delivered_customer_date,
			o.order_estimated_delivery_date
		FROM silver.erp_olist_order_items_dataset oi
		JOIN silver.oms_olist_orders_dataset o ON o.order_id = oi.order_id
		LEFT JOIN order_totals ot ON ot.order_id = oi.order_id
		LEFT JOIN payment_totals pt ON pt.order_id = oi.order_id
		LEFT JOIN main_payment mp ON mp.order_id = oi.order_id AND mp.rn = 1
		LEFT JOIN latest_review lr ON lr.order_id = oi.order_id AND lr.rn = 1
		LEFT JOIN gold.v_dim_date dd ON dd.full_date = CAST(o.order_purchase_timestamp AS DATE)
		LEFT JOIN gold.v_dim_customer dc ON dc.customer_id = o.customer_id
		LEFT JOIN gold.v_dim_seller ds ON ds.seller_id = oi.seller_id
		LEFT JOIN gold.v_dim_product dp ON dp.product_id = oi.product_id
		LEFT JOIN gold.v_dim_payment_type dpt ON dpt.payment_type = mp.payment_type
		-- weather at the seller's city on the day the order was handed to the carrier
		LEFT JOIN gold.v_dim_weather dw
			ON dw.weather_date = CAST(o.order_delivered_carrier_date AS DATE)
			AND dw.city_name = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(ds.seller_city,
				'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o')
	)
	MERGE gold.fact_orders AS t
	USING staging AS s
		ON t.order_id = s.order_id AND t.order_item_id = s.order_item_id
	WHEN MATCHED THEN UPDATE SET
		date_key                        = s.date_key,
		customer_key                    = s.customer_key,
		seller_key                      = s.seller_key,
		product_key                     = s.product_key,
		payment_type_key                = s.payment_type_key,
		weather_key                     = s.weather_key,
		line_item_price                 = s.line_item_price,
		line_item_freight               = s.line_item_freight,
		allocated_payment_value         = s.allocated_payment_value,
		review_score                    = s.review_score,
		order_status                    = s.order_status,
		delivery_delay_days             = s.delivery_delay_days,
		transit_days                    = s.transit_days,
		order_to_delivery_days          = s.order_to_delivery_days,
		order_purchase_timestamp        = s.order_purchase_timestamp,
		order_approved_at               = s.order_approved_at,
		order_delivered_carrier_date    = s.order_delivered_carrier_date,
		order_delivered_customer_date   = s.order_delivered_customer_date,
		order_estimated_delivery_date   = s.order_estimated_delivery_date
	WHEN NOT MATCHED BY TARGET THEN INSERT (
		order_id, order_item_id, date_key, customer_key, seller_key, product_key,
		payment_type_key, weather_key, line_item_price, line_item_freight,
		allocated_payment_value, review_score, order_status, delivery_delay_days,
		transit_days, order_to_delivery_days, order_purchase_timestamp, order_approved_at,
		order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date
	)
	VALUES (
		s.order_id, s.order_item_id, s.date_key, s.customer_key, s.seller_key, s.product_key,
		s.payment_type_key, s.weather_key, s.line_item_price, s.line_item_freight,
		s.allocated_payment_value, s.review_score, s.order_status, s.delivery_delay_days,
		s.transit_days, s.order_to_delivery_days, s.order_purchase_timestamp, s.order_approved_at,
		s.order_delivered_carrier_date, s.order_delivered_customer_date, s.order_estimated_delivery_date
	)
	WHEN NOT MATCHED BY SOURCE THEN DELETE;

	DECLARE @rows INT = (SELECT COUNT(*) FROM gold.fact_orders);
	PRINT 'gold.fact_orders: ' + FORMAT(@rows, 'N0') + ' rows in '
		+ CAST(DATEDIFF(SECOND, @start, SYSDATETIME()) AS VARCHAR(10)) + 's';
END;
GO
