-- ============================================================================
-- Gold Layer: Incremental Load Fact Table Procedure
-- ============================================================================

CREATE OR ALTER PROCEDURE gold.load_fact_orders
AS
BEGIN
    SET NOCOUNT ON;

    -- Staging: Build the new/updated records
    WITH order_totals AS (
        SELECT
            order_id,
            SUM(price) AS total_order_price
        FROM silver.erp_olist_order_items_dataset
        GROUP BY order_id
    ),
    payment_totals AS (
        SELECT
            order_id,
            SUM(payment_value) AS total_payment_value
        FROM silver.oms_olist_order_payments_dataset
        GROUP BY order_id
    ),
    primary_payment_type AS (
        SELECT
            order_id,
            payment_type,
            ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY payment_value DESC) AS rn
        FROM silver.oms_olist_order_payments_dataset
    ),
    latest_review AS (
        SELECT
            order_id,
            review_score,
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
            coalesce(dpt.payment_type_key,-1) AS payment_type_key,
            dw.weather_key,
            oi.price AS line_item_price,
            oi.freight_value AS line_item_freight,
            CASE
                WHEN ISNULL(ot.total_order_price, 0) > 0 
                THEN (1.0 * oi.price / ot.total_order_price) * ISNULL(pt.total_payment_value, 0)
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
        INNER JOIN silver.oms_olist_orders_dataset o
            ON oi.order_id = o.order_id
        LEFT JOIN order_totals ot
            ON oi.order_id = ot.order_id
        LEFT JOIN payment_totals pt
            ON oi.order_id = pt.order_id
        LEFT JOIN primary_payment_type ppt
            ON oi.order_id = ppt.order_id AND ppt.rn = 1
        LEFT JOIN latest_review lr
            ON oi.order_id = lr.order_id AND lr.rn = 1
        LEFT JOIN gold.v_dim_date dd
            ON CAST(o.order_purchase_timestamp AS DATE) = dd.full_date
        LEFT JOIN gold.v_dim_customer dc
            ON o.customer_id = dc.customer_id
        LEFT JOIN gold.v_dim_seller ds
            ON oi.seller_id = ds.seller_id
        LEFT JOIN gold.v_dim_product dp
            ON oi.product_id = dp.product_id
        LEFT JOIN gold.v_dim_payment_type dpt
            ON ppt.payment_type = dpt.payment_type
        LEFT JOIN gold.v_dim_weather dw
            ON LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                ds.seller_city, 
                'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o'), 'ú', 'u'), 'ã', 'a'), 'õ', 'o')) = dw.city_name
            AND CAST(o.order_delivered_carrier_date AS DATE) = dw.weather_date
    )
    -- MERGE: Update existing, insert new
    MERGE gold.fact_orders AS target
    USING staging AS source
        ON target.order_id = source.order_id 
        AND target.order_item_id = source.order_item_id
    
    -- When row exists but data changed, update it
    WHEN MATCHED THEN
        UPDATE SET
            date_key = source.date_key,
            customer_key = source.customer_key,
            seller_key = source.seller_key,
            product_key = source.product_key,
            payment_type_key = source.payment_type_key,
            weather_key = source.weather_key,
            line_item_price = source.line_item_price,
            line_item_freight = source.line_item_freight,
            allocated_payment_value = source.allocated_payment_value,
            review_score = source.review_score,
            order_status = source.order_status,
            delivery_delay_days = source.delivery_delay_days,
            transit_days = source.transit_days,
            order_to_delivery_days = source.order_to_delivery_days,
            order_purchase_timestamp = source.order_purchase_timestamp,
            order_approved_at = source.order_approved_at,
            order_delivered_carrier_date = source.order_delivered_carrier_date,
            order_delivered_customer_date = source.order_delivered_customer_date,
            order_estimated_delivery_date = source.order_estimated_delivery_date
    
    -- When row doesn't exist, insert it
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (
            order_id,
            order_item_id,
            date_key,
            customer_key,
            seller_key,
            product_key,
            payment_type_key,
            weather_key,
            line_item_price,
            line_item_freight,
            allocated_payment_value,
            review_score,
            order_status,
            delivery_delay_days,
            transit_days,
            order_to_delivery_days,
            order_purchase_timestamp,
            order_approved_at,
            order_delivered_carrier_date,
            order_delivered_customer_date,
            order_estimated_delivery_date
        )
        VALUES (
            source.order_id,
            source.order_item_id,
            source.date_key,
            source.customer_key,
            source.seller_key,
            source.product_key,
            source.payment_type_key,
            source.weather_key,
            source.line_item_price,
            source.line_item_freight,
            source.allocated_payment_value,
            source.review_score,
            source.order_status,
            source.delivery_delay_days,
            source.transit_days,
            source.order_to_delivery_days,
            source.order_purchase_timestamp,
            source.order_approved_at,
            source.order_delivered_carrier_date,
            source.order_delivered_customer_date,
            source.order_estimated_delivery_date
        )
    
    -- When row exists in fact but not in source, delete it
    WHEN NOT MATCHED BY SOURCE THEN
        DELETE;

    -- Return summary
    SELECT 
        'Fact table loaded (incremental)' AS status,
        COUNT(*) AS row_count,
        GETDATE() AS load_timestamp
    FROM gold.fact_orders;
END;
GO

--EXEc gold.load_fact_orders

