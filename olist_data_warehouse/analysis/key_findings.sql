/*
	Queries behind the Key Findings in the README.
	Unit of analysis: one delivered order with a review.
	"Late" means delivered after the estimated delivery date.
*/

USE Olist_DWP;
GO

SET NOCOUNT ON;
DROP TABLE IF EXISTS #orders, #dates;

SELECT * INTO #dates FROM gold.v_dim_date;
CREATE UNIQUE CLUSTERED INDEX ix_dates ON #dates (date_key);

SELECT
	f.order_id,
	MAX(f.review_score)                                                     AS review,
	MAX(f.delivery_delay_days)                                              AS delay_days,
	MAX(f.transit_days)                                                     AS transit_days,
	MAX(f.order_to_delivery_days)                                           AS total_days,
	MIN(f.date_key)                                                         AS date_key,
	MIN(f.weather_key)                                                      AS weather_key,
	MAX(CASE WHEN s.seller_state <> c.customer_state THEN 1 ELSE 0 END)     AS cross_state,
	COUNT(DISTINCT f.seller_key)                                            AS sellers,
	MAX(CASE WHEN f.delivery_delay_days > 0 THEN 1 ELSE 0 END)              AS is_late
INTO #orders
FROM gold.fact_orders f
JOIN gold.v_dim_customer c ON c.customer_key = f.customer_key
JOIN gold.v_dim_seller s ON s.seller_key = f.seller_key
WHERE f.order_status = 'delivered'
	AND f.order_delivered_customer_date IS NOT NULL
	AND f.review_score IS NOT NULL
GROUP BY f.order_id;

-- 1. delivery delay vs review score
SELECT
	CASE
		WHEN delay_days <= -10 THEN '1. 10+ days early'
		WHEN delay_days <= 0   THEN '2. 0-9 days early'
		WHEN delay_days <= 3   THEN '3. 1-3 days late'
		WHEN delay_days <= 7   THEN '4. 4-7 days late'
		ELSE '5. 8+ days late'
	END                                                         AS delivery,
	COUNT(*)                                                    AS orders,
	CAST(AVG(review * 1.0) AS DECIMAL(3,2))                     AS avg_review,
	CAST(AVG(CASE WHEN review <= 2 THEN 100.0 ELSE 0 END) AS DECIMAL(4,1)) AS pct_1_2_stars
FROM #orders
GROUP BY
	CASE
		WHEN delay_days <= -10 THEN '1. 10+ days early'
		WHEN delay_days <= 0   THEN '2. 0-9 days early'
		WHEN delay_days <= 3   THEN '3. 1-3 days late'
		WHEN delay_days <= 7   THEN '4. 4-7 days late'
		ELSE '5. 8+ days late'
	END
ORDER BY delivery;

-- 2. seller and customer in the same state or not
SELECT
	CASE WHEN cross_state = 1 THEN 'different state' ELSE 'same state' END AS route,
	COUNT(*)                                                    AS orders,
	CAST(AVG(transit_days * 1.0) AS DECIMAL(4,1))               AS avg_transit_days,
	CAST(AVG(is_late * 100.0) AS DECIMAL(4,1))                  AS pct_late,
	CAST(AVG(review * 1.0) AS DECIMAL(3,2))                     AS avg_review
FROM #orders
GROUP BY cross_state;

-- 3. orders split across several sellers
SELECT
	CASE WHEN sellers > 1 THEN '2+ sellers' ELSE '1 seller' END AS sellers_in_order,
	COUNT(*)                                                    AS orders,
	CAST(AVG(is_late * 100.0) AS DECIMAL(4,1))                  AS pct_late,
	CAST(AVG(review * 1.0) AS DECIMAL(3,2))                     AS avg_review,
	CAST(AVG(CASE WHEN review <= 2 THEN 100.0 ELSE 0 END) AS DECIMAL(4,1)) AS pct_1_2_stars
FROM #orders
GROUP BY CASE WHEN sellers > 1 THEN '2+ sellers' ELSE '1 seller' END;

-- 4. rain in the seller's city on the day the order was handed to the carrier
SELECT
	w.precipitation_category                                    AS rain_at_dispatch,
	COUNT(*)                                                    AS orders,
	CAST(AVG(o.transit_days * 1.0) AS DECIMAL(4,1))             AS avg_transit_days,
	CAST(AVG(o.is_late * 100.0) AS DECIMAL(4,1))                AS pct_late,
	CAST(AVG(o.review * 1.0) AS DECIMAL(3,2))                   AS avg_review
FROM #orders o
JOIN gold.v_dim_weather w ON w.weather_key = o.weather_key
GROUP BY w.precipitation_category
ORDER BY pct_late;

-- 5. holidays: purchase day, and a holiday in the week after purchase
SELECT
	CASE WHEN d.is_holiday = 1 THEN 'holiday' WHEN d.is_weekend = 1 THEN 'weekend' ELSE 'weekday' END AS purchase_day,
	COUNT(*)                                                    AS orders,
	CAST(AVG(o.total_days * 1.0) AS DECIMAL(4,1))               AS avg_days_to_deliver,
	CAST(AVG(o.is_late * 100.0) AS DECIMAL(4,1))                AS pct_late,
	CAST(AVG(o.review * 1.0) AS DECIMAL(3,2))                   AS avg_review
FROM #orders o
JOIN #dates d ON d.date_key = o.date_key
GROUP BY CASE WHEN d.is_holiday = 1 THEN 'holiday' WHEN d.is_weekend = 1 THEN 'weekend' ELSE 'weekday' END;

SELECT
	CASE WHEN h.has_holiday = 1 THEN 'yes' ELSE 'no' END        AS holiday_in_next_7_days,
	COUNT(*)                                                    AS orders,
	CAST(AVG(o.total_days * 1.0) AS DECIMAL(4,1))               AS avg_days_to_deliver,
	CAST(AVG(o.is_late * 100.0) AS DECIMAL(4,1))                AS pct_late
FROM #orders o
JOIN #dates d ON d.date_key = o.date_key
CROSS APPLY (
	SELECT MAX(x.is_holiday) AS has_holiday
	FROM #dates x
	WHERE x.full_date > d.full_date AND x.full_date <= DATEADD(DAY, 7, d.full_date)
) h
GROUP BY h.has_holiday;

-- 6. month by month: exchange rate, demand, lateness and reviews
WITH monthly AS (
	SELECT
		d.year,
		d.month,
		AVG(d.brl_usd_rate)             AS brl_usd,
		COUNT(*)                        AS orders,
		AVG(o.is_late * 100.0)          AS pct_late,
		AVG(o.review * 1.0)             AS avg_review
	FROM #orders o
	JOIN #dates d ON d.date_key = o.date_key
	WHERE d.full_date >= '2017-01-01' AND d.full_date < '2018-09-01'
	GROUP BY d.year, d.month
)
SELECT
	year,
	month,
	CAST(brl_usd AS DECIMAL(5,3))       AS brl_usd,
	orders,
	CAST(pct_late AS DECIMAL(4,1))      AS pct_late,
	CAST(avg_review AS DECIMAL(3,2))    AS avg_review
FROM monthly
ORDER BY year, month;

-- 7. correlations (Pearson)
SELECT
	'order level' AS level,
	CAST((AVG(total_days * 1.0 * review) - AVG(total_days * 1.0) * AVG(review * 1.0))
		/ (STDEVP(total_days * 1.0) * STDEVP(review * 1.0)) AS DECIMAL(4,2)) AS days_to_deliver_vs_review,
	CAST((AVG(delay_days * 1.0 * review) - AVG(delay_days * 1.0) * AVG(review * 1.0))
		/ (STDEVP(delay_days * 1.0) * STDEVP(review * 1.0)) AS DECIMAL(4,2)) AS delay_vs_review
FROM #orders;

SELECT
	'rain mm at dispatch' AS level,
	CAST((AVG(w.precipitation_mm * o.transit_days) - AVG(w.precipitation_mm) * AVG(o.transit_days * 1.0))
		/ (STDEVP(w.precipitation_mm) * STDEVP(o.transit_days * 1.0)) AS DECIMAL(4,2)) AS rain_vs_transit_days
FROM #orders o
JOIN gold.v_dim_weather w ON w.weather_key = o.weather_key;
GO
