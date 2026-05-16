-- ============================================================================
-- Gold Layer: Optimized Indexes for Analytics Performance
-- ============================================================================

USE Olist_DWP;
GO


-- ============================================================================
-- FACT TABLE INDEXES
-- ============================================================================

-- Date dimension (most common filter in analytics)
CREATE NONCLUSTERED INDEX IX_fact_orders_date_key 
    ON gold.fact_orders(date_key)
    INCLUDE (line_item_price, line_item_freight, allocated_payment_value, 
             review_score, delivery_delay_days, transit_days)
    WHERE date_key IS NOT NULL;

-- Customer dimension (customer analysis)
CREATE NONCLUSTERED INDEX IX_fact_orders_customer_key 
    ON gold.fact_orders(customer_key)
    INCLUDE (date_key, line_item_price, allocated_payment_value, review_score)
    WHERE customer_key IS NOT NULL;

-- Seller dimension (seller performance analysis)
CREATE NONCLUSTERED INDEX IX_fact_orders_seller_key 
    ON gold.fact_orders(seller_key)
    INCLUDE (date_key, line_item_price, allocated_payment_value, 
             delivery_delay_days, transit_days, review_score)
    WHERE seller_key IS NOT NULL;

-- Product dimension (product analysis)
CREATE NONCLUSTERED INDEX IX_fact_orders_product_key 
    ON gold.fact_orders(product_key)
    INCLUDE (date_key, seller_key, line_item_price, allocated_payment_value, review_score)
    WHERE product_key IS NOT NULL;

-- Payment type dimension
CREATE NONCLUSTERED INDEX IX_fact_orders_payment_type_key 
    ON gold.fact_orders(payment_type_key)
    INCLUDE (date_key, allocated_payment_value)
    WHERE payment_type_key IS NOT NULL;

-- Weather dimension (weather impact analysis)
CREATE NONCLUSTERED INDEX IX_fact_orders_weather_key 
    ON gold.fact_orders(weather_key)
    INCLUDE (date_key, seller_key, delivery_delay_days, transit_days)
    WHERE weather_key IS NOT NULL;

-- Order ID lookup (tracing back to source)
CREATE NONCLUSTERED INDEX IX_fact_orders_order_id 
    ON gold.fact_orders(order_id)
    INCLUDE (order_item_id, date_key);

-- Order status filtering (delivered vs cancelled analysis)
CREATE NONCLUSTERED INDEX IX_fact_orders_order_status 
    ON gold.fact_orders(order_status)
    INCLUDE (date_key, delivery_delay_days, transit_days, review_score);

-- Composite: Date + Customer (common Power BI query pattern)
CREATE NONCLUSTERED INDEX IX_fact_orders_date_customer 
    ON gold.fact_orders(date_key, customer_key)
    INCLUDE (line_item_price, allocated_payment_value)
    WHERE date_key IS NOT NULL AND customer_key IS NOT NULL;

-- Composite: Date + Seller (seller performance over time)
CREATE NONCLUSTERED INDEX IX_fact_orders_date_seller 
    ON gold.fact_orders(date_key, seller_key)
    INCLUDE (line_item_price, allocated_payment_value, delivery_delay_days)
    WHERE date_key IS NOT NULL AND seller_key IS NOT NULL;

-- Composite: Date + Product (product sales trends)
CREATE NONCLUSTERED INDEX IX_fact_orders_date_product 
    ON gold.fact_orders(date_key, product_key)
    INCLUDE (line_item_price, allocated_payment_value)
    WHERE date_key IS NOT NULL AND product_key IS NOT NULL;

-- Review analysis (customer satisfaction queries)
CREATE NONCLUSTERED INDEX IX_fact_orders_review_score 
    ON gold.fact_orders(review_score)
    INCLUDE (date_key, seller_key, product_key, delivery_delay_days)
    WHERE review_score IS NOT NULL;

-- Delivery performance analysis (late deliveries)
CREATE NONCLUSTERED INDEX IX_fact_orders_delivery_delay 
    ON gold.fact_orders(delivery_delay_days)
    INCLUDE (date_key, seller_key, weather_key, review_score)
    WHERE delivery_delay_days IS NOT NULL;

GO

PRINT 'Gold layer indexes created successfully';
PRINT 'Total fact table indexes created: 13';