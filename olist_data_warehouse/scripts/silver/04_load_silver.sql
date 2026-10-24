/*
	Loads silver from bronze. Every table is truncated and reloaded.
	EXEC silver.load_silver;
*/

USE Olist_DWP;
GO

CREATE OR ALTER PROCEDURE silver.load_silver
AS
BEGIN
	SET NOCOUNT ON;

	DECLARE @start DATETIME2 = SYSDATETIME(), @step NVARCHAR(128);
	DECLARE @fx_min DATE, @fx_max DATE;

	BEGIN TRY

		-- CRM

		SET @step = 'silver.crm_olist_customers_dataset';
		TRUNCATE TABLE silver.crm_olist_customers_dataset;
		INSERT INTO silver.crm_olist_customers_dataset (customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state)
		SELECT
			customer_id,
			customer_unique_id,
			TRIM(customer_zip_code_prefix),
			LOWER(TRIM(customer_city)),
			UPPER(TRIM(customer_state))
		FROM bronze.crm_olist_customers_dataset;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		-- one row per zip code, preferring a coordinate that falls inside Brazil
		SET @step = 'silver.crm_olist_geolocation_dataset';
		TRUNCATE TABLE silver.crm_olist_geolocation_dataset;
		WITH ranked AS (
			SELECT
				*,
				CASE WHEN geolocation_lat BETWEEN -33 AND 5 AND geolocation_lng BETWEEN -74 AND -34 THEN 1 ELSE 0 END AS in_brazil,
				ROW_NUMBER() OVER (
					PARTITION BY geolocation_zip_code_prefix
					ORDER BY
						CASE WHEN geolocation_lat BETWEEN -33 AND 5 AND geolocation_lng BETWEEN -74 AND -34 THEN 0 ELSE 1 END,
						geolocation_lat,
						geolocation_lng
				) AS rn
			FROM bronze.crm_olist_geolocation_dataset
		)
		INSERT INTO silver.crm_olist_geolocation_dataset (geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state, is_valid_coordinate)
		SELECT
			TRIM(geolocation_zip_code_prefix),
			geolocation_lat,
			geolocation_lng,
			LOWER(TRIM(geolocation_city)),
			UPPER(TRIM(geolocation_state)),
			in_brazil
		FROM ranked
		WHERE rn = 1;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		SET @step = 'silver.crm_olist_sellers_dataset';
		TRUNCATE TABLE silver.crm_olist_sellers_dataset;
		INSERT INTO silver.crm_olist_sellers_dataset (seller_id, seller_zip_code_prefix, seller_city, seller_state)
		SELECT
			seller_id,
			TRIM(seller_zip_code_prefix),
			LOWER(TRIM(seller_city)),
			UPPER(TRIM(seller_state))
		FROM bronze.crm_olist_sellers_dataset;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		-- ERP

		SET @step = 'silver.erp_olist_order_items_dataset';
		TRUNCATE TABLE silver.erp_olist_order_items_dataset;
		INSERT INTO silver.erp_olist_order_items_dataset (order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value)
		SELECT order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value
		FROM bronze.erp_olist_order_items_dataset;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		SET @step = 'silver.erp_olist_products_dataset';
		TRUNCATE TABLE silver.erp_olist_products_dataset;
		INSERT INTO silver.erp_olist_products_dataset (
			product_id, product_category_name, product_category_name_english,
			product_name_length, product_description_length, product_photos_qty,
			product_weight_g, product_length_cm, product_height_cm, product_width_cm
		)
		SELECT
			p.product_id,
			p.product_category_name,
			COALESCE(t.product_category_name_english, o.product_category_name_english, 'unknown'),
			p.product_name_lenght,
			p.product_description_lenght,
			p.product_photos_qty,
			p.product_weight_g,
			p.product_length_cm,
			p.product_height_cm,
			p.product_width_cm
		FROM bronze.erp_olist_products_dataset p
		LEFT JOIN bronze.erp_product_category_name_translation t ON t.product_category_name = p.product_category_name
		LEFT JOIN silver.ref_category_translations_override o ON o.product_category_name = p.product_category_name;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		SET @step = 'silver.erp_product_category_name_translation';
		TRUNCATE TABLE silver.erp_product_category_name_translation;
		INSERT INTO silver.erp_product_category_name_translation (product_category_name, product_category_name_english)
		SELECT TRIM(product_category_name), TRIM(product_category_name_english)
		FROM bronze.erp_product_category_name_translation;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		-- OMS

		SET @step = 'silver.oms_olist_orders_dataset';
		TRUNCATE TABLE silver.oms_olist_orders_dataset;
		INSERT INTO silver.oms_olist_orders_dataset (
			order_id, customer_id, order_status,
			order_purchase_timestamp, order_approved_at, order_delivered_carrier_date,
			order_delivered_customer_date, order_estimated_delivery_date,
			delivery_delay_days, transit_days, order_to_delivery_days
		)
		SELECT
			order_id,
			customer_id,
			TRIM(order_status),
			order_purchase_timestamp,
			order_approved_at,
			order_delivered_carrier_date,
			order_delivered_customer_date,
			order_estimated_delivery_date,
			DATEDIFF(DAY, order_estimated_delivery_date, order_delivered_customer_date),
			DATEDIFF(DAY, order_delivered_carrier_date, order_delivered_customer_date),
			DATEDIFF(DAY, order_purchase_timestamp, order_delivered_customer_date)
		FROM bronze.oms_olist_orders_dataset;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		-- review_id repeats in the source; extra copies are flagged, not removed
		SET @step = 'silver.oms_olist_orders_reviews_dataset';
		TRUNCATE TABLE silver.oms_olist_orders_reviews_dataset;
		WITH ranked AS (
			SELECT *, ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY review_answer_timestamp DESC) AS rn
			FROM bronze.oms_olist_orders_reviews_dataset
		)
		INSERT INTO silver.oms_olist_orders_reviews_dataset (
			review_id, order_id, review_score, review_comment_title, review_comment_message,
			review_creation_date, review_answer_timestamp, is_duplicate_review_id
		)
		SELECT
			review_id,
			order_id,
			review_score,
			NULLIF(TRIM(CHAR(13) + CHAR(10) + CHAR(9) + ' ' FROM review_comment_title), ''),
			NULLIF(TRIM(CHAR(13) + CHAR(10) + CHAR(9) + ' ' FROM review_comment_message), ''),
			review_creation_date,
			review_answer_timestamp,
			CASE WHEN rn > 1 THEN 1 ELSE 0 END
		FROM ranked;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		SET @step = 'silver.oms_olist_order_payments_dataset';
		TRUNCATE TABLE silver.oms_olist_order_payments_dataset;
		INSERT INTO silver.oms_olist_order_payments_dataset (order_id, payment_sequential, payment_type, payment_installments, payment_value, is_valid_payment_type)
		SELECT
			order_id,
			payment_sequential,
			TRIM(payment_type),
			payment_installments,
			payment_value,
			CASE WHEN TRIM(payment_type) = 'not_defined' THEN 0 ELSE 1 END
		FROM bronze.oms_olist_order_payments_dataset;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		-- Enrichment

		SET @step = 'silver.ext_weather_consolidated';
		TRUNCATE TABLE silver.ext_weather_consolidated;
		INSERT INTO silver.ext_weather_consolidated (city_name, weather_date, temp_max_c, temp_min_c, precipitation_mm, windspeed_max_kmh)
		SELECT TRIM(city_name), weather_date, temp_max_c, temp_min_c, precipitation_mm, windspeed_max_kmh
		FROM bronze.ext_weather_consolidated;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		-- FRED has no rows for weekends and holidays, so build a full calendar and
		-- carry the last known rate forward. COUNT() only increases on days with a
		-- rate, which groups each gap with the rate before it.
		SET @step = 'silver.ext_dexbzus';
		TRUNCATE TABLE silver.ext_dexbzus;

		SELECT
			@fx_min = MIN(TRY_CONVERT(DATE, observation_date, 103)),
			@fx_max = MAX(TRY_CONVERT(DATE, observation_date, 103))
		FROM bronze.ext_dexbzus;

		WITH calendar AS (
			SELECT @fx_min AS dt
			UNION ALL
			SELECT DATEADD(DAY, 1, dt) FROM calendar WHERE dt < @fx_max
		),
		rates AS (
			SELECT
				TRY_CONVERT(DATE, observation_date, 103) AS observation_date,
				TRY_CAST(DEXBZUS AS DECIMAL(10,4)) AS brl_usd_rate
			FROM bronze.ext_dexbzus
		),
		grouped AS (
			SELECT
				c.dt,
				r.brl_usd_rate,
				COUNT(r.brl_usd_rate) OVER (ORDER BY c.dt ROWS UNBOUNDED PRECEDING) AS grp
			FROM calendar c
			LEFT JOIN rates r ON r.observation_date = c.dt
		)
		INSERT INTO silver.ext_dexbzus (observation_date, brl_usd_rate, is_forward_filled)
		SELECT
			dt,
			MAX(brl_usd_rate) OVER (PARTITION BY grp),
			CASE WHEN brl_usd_rate IS NULL THEN 1 ELSE 0 END
		FROM grouped
		OPTION (MAXRECURSION 0);
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		SET @step = 'silver.ext_macro_factors';
		TRUNCATE TABLE silver.ext_macro_factors;
		INSERT INTO silver.ext_macro_factors (year, gdp_usd, inflation_pct, unemployment_pct, gdp_capita_usd)
		SELECT year, gdp_usd, inflation_pct, unemployment_pct, gdp_capita_usd
		FROM bronze.ext_macro_factors;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		-- population comes as text like 22,728 or 43.935(2)
		SET @step = 'silver.ext_municipal_population_est';
		TRUNCATE TABLE silver.ext_municipal_population_est;
		INSERT INTO silver.ext_municipal_population_est (uf, cod_uf, cod_munic, nome_municipio, populacao_estimada)
		SELECT
			UPPER(TRIM(uf)),
			cod_uf,
			TRIM(cod_munic),
			TRIM(nome_municipio),
			CAST(
				REPLACE(REPLACE(REPLACE(
					LEFT(TRIM(populacao_estimada), CHARINDEX('(', TRIM(populacao_estimada) + '(') - 1),
				',', ''), '.', ''), ' ', '')
			AS INT)
		FROM bronze.ext_municipal_population_est;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		SET @step = 'silver.ext_brazil_holidays';
		TRUNCATE TABLE silver.ext_brazil_holidays;
		INSERT INTO silver.ext_brazil_holidays (holiday_date, local_name, name, country_code, is_fixed, is_global, holiday_type, holiday_type_2)
		SELECT
			CONVERT(DATE, date, 103),
			TRIM(localName),
			TRIM(name),
			TRIM(countryCode),
			CASE WHEN TRIM(fixed) = 'TRUE' THEN 1 ELSE 0 END,
			CASE WHEN TRIM(global) = 'TRUE' THEN 1 ELSE 0 END,
			TRIM(types_0),
			TRIM(types_1)
		FROM bronze.ext_brazil_holidays;
		PRINT @step + ': ' + FORMAT(@@ROWCOUNT, 'N0') + ' rows';

		PRINT 'Silver loaded in ' + CAST(DATEDIFF(SECOND, @start, SYSDATETIME()) AS VARCHAR(10)) + 's';

	END TRY
	BEGIN CATCH
		PRINT 'Silver load failed on ' + @step;
		THROW;
	END CATCH
END;
GO
