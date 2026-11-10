/*
	Semantic views for Askit, built on the gold layer.
	Revenue is price + freight. Reviews, lateness and status count once per order.
*/

USE Olist_DWP;
GO

-- one row per order line
CREATE OR ALTER VIEW chatbot.v_orders_full
AS
SELECT
	f.fact_key,
	f.order_id,
	f.order_item_id,

	d.full_date                                             AS order_date,
	d.year                                                  AS order_year,
	d.month                                                 AS order_month,
	d.month_name                                            AS order_month_name,
	d.quarter                                               AS order_quarter,
	d.is_weekend                                            AS ordered_on_weekend,

	c.customer_unique_id,
	c.customer_city,
	c.customer_state,
	c.city_size_band                                        AS customer_city_size,

	s.seller_id,
	s.seller_city,
	s.seller_state,
	s.city_size_band                                        AS seller_city_size,

	p.product_category_name_english                         AS product_category,
	p.product_weight_g,
	p.volume_cm3                                            AS product_volume_cm3,

	pt.payment_type_display                                 AS payment_type,

	f.line_item_price,
	f.line_item_freight,
	f.line_item_price + f.line_item_freight                 AS revenue_brl,

	f.review_score,
	CASE
		WHEN f.review_score >= 4 THEN 'Positive'
		WHEN f.review_score = 3  THEN 'Neutral'
		WHEN f.review_score <= 2 THEN 'Negative'
		ELSE 'No Review'
	END                                                     AS review_sentiment,

	f.order_status,
	CASE f.order_status
		WHEN 'delivered'   THEN 'Delivered'
		WHEN 'shipped'     THEN 'Shipped'
		WHEN 'canceled'    THEN 'Cancelled'
		WHEN 'invoiced'    THEN 'Invoiced'
		WHEN 'processing'  THEN 'Processing'
		WHEN 'approved'    THEN 'Approved'
		WHEN 'unavailable' THEN 'Unavailable'
		ELSE f.order_status
	END                                                     AS order_status_label,

	f.delivery_delay_days,
	f.transit_days,
	f.order_to_delivery_days,
	CASE WHEN f.delivery_delay_days > 0 THEN 1 ELSE 0 END   AS is_late,
	CASE
		WHEN f.order_status <> 'delivered'                 THEN 'Not Delivered'
		WHEN f.delivery_delay_days IS NULL                 THEN 'Unknown'
		WHEN f.delivery_delay_days <= -3                   THEN 'Early'
		WHEN f.delivery_delay_days BETWEEN -2 AND 0        THEN 'On Time'
		WHEN f.delivery_delay_days BETWEEN 1 AND 5         THEN 'Slightly Late'
		ELSE 'Very Late'
	END                                                     AS delivery_performance,

	d.brl_usd_rate,
	(f.line_item_price + f.line_item_freight)
		/ NULLIF(d.brl_usd_rate, 0)                         AS revenue_usd,

	w.temp_avg_c,
	w.precipitation_category,
	w.temp_category,

	f.order_purchase_timestamp,
	f.order_delivered_customer_date,
	f.order_estimated_delivery_date
FROM gold.fact_orders f
LEFT JOIN gold.v_dim_date d          ON f.date_key = d.date_key
LEFT JOIN gold.v_dim_customer c      ON f.customer_key = c.customer_key
LEFT JOIN gold.v_dim_seller s        ON f.seller_key = s.seller_key
LEFT JOIN gold.v_dim_product p       ON f.product_key = p.product_key
LEFT JOIN gold.v_dim_payment_type pt ON f.payment_type_key = pt.payment_type_key
LEFT JOIN gold.v_dim_weather w       ON f.weather_key = w.weather_key;
GO

-- one row per customer, fulfilled orders only
CREATE OR ALTER VIEW chatbot.v_customer_summary
AS
WITH dataset_end AS (
	SELECT CAST(MAX(order_purchase_timestamp) AS DATE) AS end_date
	FROM gold.fact_orders
),
customer_orders AS (
	SELECT
		c.customer_unique_id,
		f.order_id,
		MAX(c.customer_city)                                        AS customer_city,
		MAX(c.customer_state)                                       AS customer_state,
		MAX(c.city_size_band)                                       AS city_size_band,
		MAX(f.order_purchase_timestamp)                             AS order_purchase_timestamp,
		COUNT(*)                                                    AS line_items,
		SUM(f.line_item_price + f.line_item_freight)                AS order_revenue_brl,
		MAX(f.review_score)                                         AS review_score,
		MAX(CASE WHEN f.delivery_delay_days > 0 THEN 1 ELSE 0 END)  AS is_late,
		MAX(f.order_to_delivery_days)                               AS order_to_delivery_days
	FROM gold.fact_orders f
	JOIN gold.v_dim_customer c ON f.customer_key = c.customer_key
	WHERE f.order_status NOT IN ('canceled', 'unavailable')
	GROUP BY c.customer_unique_id, f.order_id
),
-- latest address
latest_location AS (
	SELECT
		customer_unique_id,
		customer_city,
		customer_state,
		city_size_band,
		ROW_NUMBER() OVER (
			PARTITION BY customer_unique_id
			ORDER BY order_purchase_timestamp DESC, order_id
		) AS rn
	FROM customer_orders
),
categories AS (
	SELECT
		c.customer_unique_id,
		COUNT(DISTINCT p.product_category_name_english) AS distinct_categories_purchased
	FROM gold.fact_orders f
	JOIN gold.v_dim_customer c     ON f.customer_key = c.customer_key
	LEFT JOIN gold.v_dim_product p ON f.product_key = p.product_key
	WHERE f.order_status NOT IN ('canceled', 'unavailable')
	GROUP BY c.customer_unique_id
),
totals AS (
	SELECT
		customer_unique_id,
		COUNT(*)                                     AS total_orders,
		SUM(line_items)                              AS total_line_items,
		SUM(order_revenue_brl)                       AS total_revenue_brl,
		AVG(order_revenue_brl)                       AS avg_order_value_brl,
		AVG(CAST(review_score AS FLOAT))             AS avg_review_score,
		SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) AS negative_reviews,
		SUM(is_late)                                 AS late_deliveries_received,
		AVG(CAST(order_to_delivery_days AS FLOAT))   AS avg_delivery_days,
		MAX(order_purchase_timestamp)                AS last_order_date,
		MIN(order_purchase_timestamp)                AS first_order_date
	FROM customer_orders
	GROUP BY customer_unique_id
)
SELECT
	t.customer_unique_id,
	l.customer_city,
	l.customer_state,
	l.city_size_band,
	t.total_orders,
	t.total_line_items,
	t.total_revenue_brl,
	t.avg_order_value_brl,
	t.avg_review_score,
	t.negative_reviews,
	t.late_deliveries_received,
	t.avg_delivery_days,
	DATEDIFF(DAY, t.last_order_date, e.end_date)  AS days_since_last_order,
	t.last_order_date,
	t.first_order_date,
	CASE
		WHEN DATEDIFF(DAY, t.last_order_date, e.end_date) > 180 AND t.total_orders = 1 THEN 'High'
		WHEN DATEDIFF(DAY, t.last_order_date, e.end_date) > 90 THEN 'Medium'
		ELSE 'Low'
	END                                           AS churn_risk,
	cat.distinct_categories_purchased
FROM totals t
JOIN latest_location l ON l.customer_unique_id = t.customer_unique_id AND l.rn = 1
JOIN categories cat    ON cat.customer_unique_id = t.customer_unique_id
CROSS JOIN dataset_end e;
GO

-- one row per seller
CREATE OR ALTER VIEW chatbot.v_seller_summary
AS
WITH seller_orders AS (
	SELECT
		s.seller_id,
		f.order_id,
		MAX(s.seller_city)                                          AS seller_city,
		MAX(s.seller_state)                                         AS seller_state,
		MAX(s.city_size_band)                                       AS city_size_band,
		MAX(f.order_status)                                         AS order_status,
		MAX(f.order_purchase_timestamp)                             AS order_purchase_timestamp,
		COUNT(*)                                                    AS line_items,
		SUM(f.line_item_price + f.line_item_freight)                AS order_revenue_brl,
		MAX(f.review_score)                                         AS review_score,
		MAX(CASE WHEN f.delivery_delay_days > 0 THEN 1 ELSE 0 END)  AS is_late,
		MAX(f.delivery_delay_days)                                  AS delivery_delay_days,
		MAX(f.transit_days)                                         AS transit_days
	FROM gold.fact_orders f
	JOIN gold.v_dim_seller s ON f.seller_key = s.seller_key
	GROUP BY s.seller_id, f.order_id
),
totals AS (
	SELECT
		seller_id,
		MAX(seller_city)                                                        AS seller_city,
		MAX(seller_state)                                                       AS seller_state,
		MAX(city_size_band)                                                     AS city_size_band,
		COUNT(*)                                                                AS total_orders,
		SUM(line_items)                                                         AS total_line_items,
		SUM(order_revenue_brl)                                                  AS total_revenue_brl,
		SUM(order_revenue_brl) / NULLIF(SUM(line_items), 0)                     AS avg_item_value_brl,
		AVG(CAST(review_score AS FLOAT))                                        AS avg_review_score,
		SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END)                      AS negative_review_count,
		SUM(CASE WHEN review_score >= 4 THEN 1 ELSE 0 END)                      AS positive_review_count,
		SUM(CASE WHEN order_status = 'delivered' AND is_late = 1 THEN 1 ELSE 0 END) AS late_delivery_count,
		SUM(CASE WHEN order_status = 'delivered' THEN 1 ELSE 0 END)             AS delivered_order_count,
		AVG(CAST(delivery_delay_days AS FLOAT))                                 AS avg_delay_days,
		AVG(CAST(transit_days AS FLOAT))                                        AS avg_transit_days,
		SUM(CASE WHEN order_status = 'canceled' THEN 1 ELSE 0 END)              AS cancelled_orders,
		MIN(order_purchase_timestamp)                                           AS first_sale_date,
		MAX(order_purchase_timestamp)                                           AS last_sale_date
	FROM seller_orders
	GROUP BY seller_id
)
SELECT
	seller_id,
	seller_city,
	seller_state,
	city_size_band,
	total_orders,
	total_line_items,
	total_revenue_brl,
	avg_item_value_brl,
	avg_review_score,
	negative_review_count,
	positive_review_count,
	late_delivery_count,
	delivered_order_count,
	ROUND(100.0 * late_delivery_count / NULLIF(delivered_order_count, 0), 1) AS late_delivery_rate_pct,
	avg_delay_days,
	avg_transit_days,
	cancelled_orders,
	CASE
		WHEN total_revenue_brl >= 50000 AND avg_review_score >= 4.0 THEN 'Platinum'
		WHEN total_revenue_brl >= 20000 AND avg_review_score >= 3.5 THEN 'Gold'
		WHEN total_revenue_brl >= 5000                              THEN 'Silver'
		ELSE 'Bronze'
	END                                                                      AS seller_tier,
	first_sale_date,
	last_sale_date
FROM totals;
GO

-- one row per category
CREATE OR ALTER VIEW chatbot.v_product_summary
AS
WITH category_items AS (
	SELECT
		p.product_category_name_english                                             AS product_category,
		COUNT(DISTINCT p.product_id)                                                AS distinct_products,
		COUNT(*)                                                                    AS total_units_sold,
		SUM(f.line_item_price + f.line_item_freight)                                AS total_revenue_brl,
		AVG(f.line_item_price)                                                      AS avg_item_price_brl,
		MIN(f.line_item_price)                                                      AS min_item_price_brl,
		MAX(f.line_item_price)                                                      AS max_item_price_brl,
		AVG(f.line_item_freight)                                                    AS avg_freight_brl,
		ROUND(100.0 * SUM(f.line_item_freight)
			/ NULLIF(SUM(f.line_item_price + f.line_item_freight), 0), 1)           AS freight_pct_of_total,
		AVG(CAST(p.product_weight_g AS FLOAT))                                      AS avg_weight_g,
		AVG(CAST(p.volume_cm3 AS FLOAT))                                            AS avg_volume_cm3
	FROM gold.fact_orders f
	JOIN gold.v_dim_product p ON f.product_key = p.product_key
	WHERE p.product_category_name_english IS NOT NULL
	GROUP BY p.product_category_name_english
),
category_orders AS (
	SELECT
		p.product_category_name_english                             AS product_category,
		f.order_id,
		MAX(f.order_status)                                         AS order_status,
		MAX(f.review_score)                                         AS review_score,
		MAX(CASE WHEN f.delivery_delay_days > 0 THEN 1 ELSE 0 END)  AS is_late,
		MAX(f.delivery_delay_days)                                  AS delivery_delay_days
	FROM gold.fact_orders f
	JOIN gold.v_dim_product p ON f.product_key = p.product_key
	WHERE p.product_category_name_english IS NOT NULL
	GROUP BY p.product_category_name_english, f.order_id
),
order_totals AS (
	SELECT
		product_category,
		COUNT(*)                                                                    AS total_orders,
		AVG(CAST(review_score AS FLOAT))                                            AS avg_review_score,
		SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END)                          AS negative_reviews,
		SUM(CASE WHEN review_score >= 4 THEN 1 ELSE 0 END)                          AS positive_reviews,
		AVG(CAST(delivery_delay_days AS FLOAT))                                     AS avg_delay_days,
		SUM(CASE WHEN order_status = 'delivered' AND is_late = 1 THEN 1 ELSE 0 END) AS late_deliveries,
		SUM(CASE WHEN order_status = 'delivered' THEN 1 ELSE 0 END)                 AS delivered_orders
	FROM category_orders
	GROUP BY product_category
)
SELECT
	i.product_category,
	i.distinct_products,
	i.total_units_sold,
	o.total_orders,
	i.total_revenue_brl,
	i.avg_item_price_brl,
	i.min_item_price_brl,
	i.max_item_price_brl,
	i.avg_freight_brl,
	i.freight_pct_of_total,
	o.avg_review_score,
	o.negative_reviews,
	o.positive_reviews,
	o.avg_delay_days,
	o.late_deliveries,
	ROUND(100.0 * o.late_deliveries / NULLIF(o.delivered_orders, 0), 1) AS late_delivery_rate_pct,
	i.avg_weight_g,
	i.avg_volume_cm3
FROM category_items i
JOIN order_totals o ON o.product_category = i.product_category;
GO

-- one row per month
CREATE OR ALTER VIEW chatbot.v_monthly_trends
AS
WITH monthly_orders AS (
	SELECT
		d.year,
		d.month,
		MAX(d.month_name)                                           AS month_name,
		MAX(d.quarter)                                              AS quarter,
		f.order_id,
		MAX(c.customer_unique_id)                                   AS customer_unique_id,
		MAX(f.order_status)                                         AS order_status,
		COUNT(*)                                                    AS line_items,
		SUM(f.line_item_price + f.line_item_freight)                AS order_revenue_brl,
		MAX(f.review_score)                                         AS review_score,
		MAX(CASE WHEN f.delivery_delay_days > 0 THEN 1 ELSE 0 END)  AS is_late
	FROM gold.fact_orders f
	JOIN gold.v_dim_date d     ON f.date_key = d.date_key
	JOIN gold.v_dim_customer c ON f.customer_key = c.customer_key
	GROUP BY d.year, d.month, f.order_id
),
-- averaged over days, not orders
monthly_macro AS (
	SELECT
		year,
		month,
		AVG(brl_usd_rate)     AS avg_brl_usd_rate,
		AVG(gdp_usd)          AS avg_gdp_usd,
		AVG(inflation_pct)    AS avg_inflation_pct,
		AVG(unemployment_pct) AS avg_unemployment_pct
	FROM gold.v_dim_date
	GROUP BY year, month
),
totals AS (
	SELECT
		year,
		month,
		MAX(month_name)                                                             AS month_name,
		MAX(quarter)                                                                AS quarter,
		COUNT(*)                                                                    AS total_orders,
		SUM(line_items)                                                             AS total_line_items,
		SUM(order_revenue_brl)                                                      AS total_revenue_brl,
		AVG(order_revenue_brl)                                                      AS avg_order_value_brl,
		SUM(CASE WHEN order_status = 'delivered' AND is_late = 1 THEN 1 ELSE 0 END) AS late_deliveries,
		SUM(CASE WHEN order_status = 'delivered' THEN 1 ELSE 0 END)                 AS delivered_orders,
		AVG(CAST(review_score AS FLOAT))                                            AS avg_review_score,
		SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END)                          AS negative_reviews,
		COUNT(DISTINCT customer_unique_id)                                          AS unique_customers
	FROM monthly_orders
	GROUP BY year, month
)
SELECT
	t.year,
	t.month,
	t.month_name,
	t.quarter,
	CAST(t.year AS VARCHAR(4)) + '-Q' + CAST(t.quarter AS VARCHAR(1))          AS year_quarter,
	t.total_orders,
	t.total_line_items,
	t.total_revenue_brl,
	t.avg_order_value_brl,
	t.late_deliveries,
	t.delivered_orders,
	ROUND(100.0 * t.late_deliveries / NULLIF(t.delivered_orders, 0), 1)        AS late_delivery_rate_pct,
	t.avg_review_score,
	t.negative_reviews,
	t.unique_customers,
	m.avg_brl_usd_rate,
	m.avg_gdp_usd,
	m.avg_inflation_pct,
	m.avg_unemployment_pct
FROM totals t
LEFT JOIN monthly_macro m ON m.year = t.year AND m.month = t.month;
GO

-- checks
DECLARE @fact_rows     INT,
		@full_rows     INT,
		@fact_revenue  DECIMAL(18, 2),
		@seller_rev    DECIMAL(18, 2),
		@monthly_rev   DECIMAL(18, 2),
		@fact_orders   INT,
		@monthly_ord   INT,
		@dupes         INT;

SELECT
	@fact_rows    = COUNT(*),
	@fact_revenue = SUM(line_item_price + line_item_freight),
	@fact_orders  = COUNT(DISTINCT order_id)
FROM gold.fact_orders;

SELECT @full_rows   = COUNT(*)               FROM chatbot.v_orders_full;
SELECT @seller_rev  = SUM(total_revenue_brl) FROM chatbot.v_seller_summary;
SELECT @monthly_rev = SUM(total_revenue_brl),
	   @monthly_ord = SUM(total_orders)      FROM chatbot.v_monthly_trends;

IF @full_rows <> @fact_rows
	THROW 50010, 'v_orders_full row count does not match gold.fact_orders.', 1;

IF ABS(@seller_rev - @fact_revenue) > 0.01
	THROW 50011, 'v_seller_summary revenue does not reconcile to gold.fact_orders.', 1;

IF ABS(@monthly_rev - @fact_revenue) > 0.01 OR @monthly_ord <> @fact_orders
	THROW 50012, 'v_monthly_trends does not reconcile to gold.fact_orders.', 1;

SELECT @dupes = COUNT(*) FROM (
	SELECT customer_unique_id FROM chatbot.v_customer_summary GROUP BY customer_unique_id HAVING COUNT(*) > 1
) x;
IF @dupes > 0 THROW 50013, 'v_customer_summary has more than one row per customer.', 1;

SELECT @dupes = COUNT(*) FROM (
	SELECT seller_id FROM chatbot.v_seller_summary GROUP BY seller_id HAVING COUNT(*) > 1
) x;
IF @dupes > 0 THROW 50014, 'v_seller_summary has more than one row per seller.', 1;

SELECT @dupes = COUNT(*) FROM (
	SELECT product_category FROM chatbot.v_product_summary GROUP BY product_category HAVING COUNT(*) > 1
) x;
IF @dupes > 0 THROW 50015, 'v_product_summary has more than one row per category.', 1;

PRINT 'All chatbot view checks passed';

SELECT 'v_orders_full'      AS view_name, COUNT(*) AS row_count FROM chatbot.v_orders_full
UNION ALL SELECT 'v_customer_summary', COUNT(*) FROM chatbot.v_customer_summary
UNION ALL SELECT 'v_seller_summary',   COUNT(*) FROM chatbot.v_seller_summary
UNION ALL SELECT 'v_product_summary',  COUNT(*) FROM chatbot.v_product_summary
UNION ALL SELECT 'v_monthly_trends',   COUNT(*) FROM chatbot.v_monthly_trends;
GO
