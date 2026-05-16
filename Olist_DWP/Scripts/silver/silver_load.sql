USE [Olist_DWP]
GO
/****** Object:  StoredProcedure [silver].[load_silver]    Script Date: 18/04/2026 6:53:42 pm ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- ============================================================
-- Stored Procedure : silver.load_silver
-- Layer            : Silver
-- Description      : Cleans and loads all silver tables from
--                    bronze. Truncates each table before load.
-- Usage            : EXEC silver.load_silver
-- ============================================================

ALTER   PROCEDURE [silver].[load_silver] AS
BEGIN
	DECLARE @start_time DATETIME, @end_time DATETIME, @batch_start_time DATETIME, @batch_end_time DATETIME;
	DECLARE @fx_min_date DATE, @fx_max_date DATE;
	BEGIN TRY
		SET @batch_start_time = GETDATE();
		PRINT '================================================';
		PRINT 'Loading Silver Layer';
		PRINT '================================================';

		-- --------------------------------------------------------
		-- CRM TABLES
		-- --------------------------------------------------------
		PRINT '------------------------------------------------';
		PRINT 'Loading CRM Tables';
		PRINT '------------------------------------------------';

		-- crm_olist_customers_dataset
		-- Transformations:
		--   - Trim whitespace on all string columns
		--   - Lowercase city names
		--   - Uppercase state codes
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.crm_olist_customers_dataset';
		TRUNCATE TABLE silver.crm_olist_customers_dataset;
		PRINT '>> Inserting Data Into: silver.crm_olist_customers_dataset';
		INSERT INTO silver.crm_olist_customers_dataset (
			customer_id,
			customer_unique_id,
			customer_zip_code_prefix,
			customer_city,
			customer_state,
			dwh_create_date
		)
		SELECT
			customer_id,
			customer_unique_id,
			TRIM(customer_zip_code_prefix)			AS customer_zip_code_prefix,
			LOWER(TRIM(customer_city))				AS customer_city,
			UPPER(TRIM(customer_state))				AS customer_state,
			GETDATE()								AS dwh_create_date
		FROM bronze.crm_olist_customers_dataset;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- crm_olist_geolocation_dataset
		-- Transformations:
		--   - Deduplicate by zip code — keep first valid Brazilian coordinate
		--   - Prioritise coordinates within Brazil bounds (-33 to +5 lat, -74 to -34 lng)
		--   - Flag out-of-bounds coordinates with is_valid_coordinate = 0
		--   - Lowercase city names, uppercase state codes
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.crm_olist_geolocation_dataset';
		TRUNCATE TABLE silver.crm_olist_geolocation_dataset;
		PRINT '>> Inserting Data Into: silver.crm_olist_geolocation_dataset';
		WITH deduped AS (
			SELECT
				geolocation_zip_code_prefix,
				geolocation_lat,
				geolocation_lng,
				geolocation_city,
				geolocation_state,
				ROW_NUMBER() OVER (
					PARTITION BY geolocation_zip_code_prefix
					ORDER BY
						CASE
							WHEN geolocation_lat BETWEEN -33 AND 5
							 AND geolocation_lng BETWEEN -74 AND -34
							THEN 0
							ELSE 1
						END,
						geolocation_lat,
						geolocation_lng
				) AS rn
			FROM bronze.crm_olist_geolocation_dataset
		)
		INSERT INTO silver.crm_olist_geolocation_dataset (
			geolocation_zip_code_prefix,
			geolocation_lat,
			geolocation_lng,
			geolocation_city,
			geolocation_state,
			is_valid_coordinate,
			dwh_create_date
		)
		SELECT
			TRIM(geolocation_zip_code_prefix)		AS geolocation_zip_code_prefix,
			geolocation_lat,
			geolocation_lng,
			LOWER(TRIM(geolocation_city))			AS geolocation_city,
			UPPER(TRIM(geolocation_state))			AS geolocation_state,
			CASE
				WHEN geolocation_lat BETWEEN -33 AND 5
				 AND geolocation_lng BETWEEN -74 AND -34
				THEN 1
				ELSE 0
			END										AS is_valid_coordinate,
			GETDATE()								AS dwh_create_date
		FROM deduped
		WHERE rn = 1;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- crm_olist_sellers_dataset
		-- Transformations:
		--   - Trim whitespace on all string columns
		--   - Lowercase city names
		--   - Uppercase state codes
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.crm_olist_sellers_dataset';
		TRUNCATE TABLE silver.crm_olist_sellers_dataset;
		PRINT '>> Inserting Data Into: silver.crm_olist_sellers_dataset';
		INSERT INTO silver.crm_olist_sellers_dataset (
			seller_id,
			seller_zip_code_prefix,
			seller_city,
			seller_state,
			dwh_create_date
		)
		SELECT
			seller_id,
			TRIM(seller_zip_code_prefix)			AS seller_zip_code_prefix,
			LOWER(TRIM(seller_city))				AS seller_city,
			UPPER(TRIM(seller_state))				AS seller_state,
			GETDATE()								AS dwh_create_date
		FROM bronze.crm_olist_sellers_dataset;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- --------------------------------------------------------
		-- ERP TABLES
		-- --------------------------------------------------------
		PRINT '------------------------------------------------';
		PRINT 'Loading ERP Tables';
		PRINT '------------------------------------------------';

		-- erp_olist_order_items_dataset
		-- Transformations:
		--   - No cleaning required — source data is clean
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.erp_olist_order_items_dataset';
		TRUNCATE TABLE silver.erp_olist_order_items_dataset;
		PRINT '>> Inserting Data Into: silver.erp_olist_order_items_dataset';
		INSERT INTO silver.erp_olist_order_items_dataset (
			order_id,
			order_item_id,
			product_id,
			seller_id,
			shipping_limit_date,
			price,
			freight_value,
			dwh_create_date
		)
		SELECT
			order_id,
			order_item_id,
			product_id,
			seller_id,
			shipping_limit_date,
			price,
			freight_value,
			GETDATE()								AS dwh_create_date
		FROM bronze.erp_olist_order_items_dataset;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- erp_olist_products_dataset
		-- Transformations:
		--   - Join English category translation from translation table
		--   - Fall back to override table for 2 missing translations
		--   - Set remaining null categories to 'unknown'
		--   - Rename misspelled columns: lenght -> length
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.erp_olist_products_dataset';
		TRUNCATE TABLE silver.erp_olist_products_dataset;
		PRINT '>> Inserting Data Into: silver.erp_olist_products_dataset';
		INSERT INTO silver.erp_olist_products_dataset (
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
			dwh_create_date
		)
		SELECT
			p.product_id,
			p.product_category_name,
			COALESCE(
				t.product_category_name_english,
				o.product_category_name_english,
				'unknown'
			)										AS product_category_name_english,
			p.product_name_lenght					AS product_name_length,
			p.product_description_lenght			AS product_description_length,
			p.product_photos_qty,
			p.product_weight_g,
			p.product_length_cm,
			p.product_height_cm,
			p.product_width_cm,
			GETDATE()								AS dwh_create_date
		FROM bronze.erp_olist_products_dataset p
		LEFT JOIN bronze.erp_product_category_name_translation t
			ON p.product_category_name = t.product_category_name
		LEFT JOIN silver.ref_category_translations_override o
			ON p.product_category_name = o.product_category_name;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- erp_product_category_name_translation
		-- Transformations:
		--   - Trim whitespace on both columns
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.erp_product_category_name_translation';
		TRUNCATE TABLE silver.erp_product_category_name_translation;
		PRINT '>> Inserting Data Into: silver.erp_product_category_name_translation';
		INSERT INTO silver.erp_product_category_name_translation (
			product_category_name,
			product_category_name_english,
			dwh_create_date
		)
		SELECT
			TRIM(product_category_name)				AS product_category_name,
			TRIM(product_category_name_english)		AS product_category_name_english,
			GETDATE()								AS dwh_create_date
		FROM bronze.erp_product_category_name_translation;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- --------------------------------------------------------
		-- OMS TABLES
		-- --------------------------------------------------------
		PRINT '------------------------------------------------';
		PRINT 'Loading OMS Tables';
		PRINT '------------------------------------------------';

		-- oms_olist_orders_dataset
		-- Transformations:
		--   - Trim order_status
		--   - Derive delivery_delay_days: actual vs estimated delivery
		--   - Derive transit_days: carrier pickup to customer delivery
		--   - Derive order_to_delivery_days: purchase to customer delivery
		--   - Null derived columns expected for cancelled/incomplete orders
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.oms_olist_orders_dataset';
		TRUNCATE TABLE silver.oms_olist_orders_dataset;
		PRINT '>> Inserting Data Into: silver.oms_olist_orders_dataset';
		INSERT INTO silver.oms_olist_orders_dataset (
			order_id,
			customer_id,
			order_status,
			order_purchase_timestamp,
			order_approved_at,
			order_delivered_carrier_date,
			order_delivered_customer_date,
			order_estimated_delivery_date,
			delivery_delay_days,
			transit_days,
			order_to_delivery_days,
			dwh_create_date
		)
		SELECT
			order_id,
			customer_id,
			TRIM(order_status)											AS order_status,
			order_purchase_timestamp,
			order_approved_at,
			order_delivered_carrier_date,
			order_delivered_customer_date,
			order_estimated_delivery_date,
			DATEDIFF(DAY, order_estimated_delivery_date,  order_delivered_customer_date)	AS delivery_delay_days,
			DATEDIFF(DAY, order_delivered_carrier_date,   order_delivered_customer_date)	AS transit_days,
			DATEDIFF(DAY, order_purchase_timestamp,       order_delivered_customer_date)	AS order_to_delivery_days,
			GETDATE()													AS dwh_create_date
		FROM bronze.oms_olist_orders_dataset;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- oms_olist_orders_reviews_dataset
		-- Transformations:
		--   - Deduplicate by review_id — keep latest by review_answer_timestamp
		--   - Flag duplicate review IDs with is_duplicate_review_id = 1
		--   - Convert empty strings to NULL on comment columns
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.oms_olist_orders_reviews_dataset';
		TRUNCATE TABLE silver.oms_olist_orders_reviews_dataset;
		PRINT '>> Inserting Data Into: silver.oms_olist_orders_reviews_dataset';
		WITH deduped AS (
			SELECT *,
				ROW_NUMBER() OVER (
					PARTITION BY review_id
					ORDER BY review_answer_timestamp DESC
				) AS rn
			FROM bronze.oms_olist_orders_reviews_dataset
		)
		INSERT INTO silver.oms_olist_orders_reviews_dataset (
			review_id,
			order_id,
			review_score,
			review_comment_title,
			review_comment_message,
			review_creation_date,
			review_answer_timestamp,
			is_duplicate_review_id,
			dwh_create_date
		)
		SELECT
			review_id,
			order_id,
			review_score,
			NULLIF(TRIM(review_comment_title),   '')	AS review_comment_title,
			NULLIF(TRIM(review_comment_message), '')	AS review_comment_message,
			review_creation_date,
			review_answer_timestamp,
			CASE WHEN rn > 1 THEN 1 ELSE 0 END			AS is_duplicate_review_id,
			GETDATE()									AS dwh_create_date
		FROM deduped;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- oms_olist_order_payments_dataset
		-- Transformations:
		--   - Trim payment_type
		--   - Flag not_defined payment types with is_valid_payment_type = 0
		--   - Zero value vouchers kept as-is — valid in source
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.oms_olist_order_payments_dataset';
		TRUNCATE TABLE silver.oms_olist_order_payments_dataset;
		PRINT '>> Inserting Data Into: silver.oms_olist_order_payments_dataset';
		INSERT INTO silver.oms_olist_order_payments_dataset (
			order_id,
			payment_sequential,
			payment_type,
			payment_installments,
			payment_value,
			is_valid_payment_type,
			dwh_create_date
		)
		SELECT
			order_id,
			payment_sequential,
			TRIM(payment_type)						AS payment_type,
			payment_installments,
			payment_value,
			CASE
				WHEN TRIM(payment_type) = 'not_defined' THEN 0
				ELSE 1
			END										AS is_valid_payment_type,
			GETDATE()								AS dwh_create_date
		FROM bronze.oms_olist_order_payments_dataset;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- --------------------------------------------------------
		-- ENRICHMENT TABLES
		-- --------------------------------------------------------
		PRINT '------------------------------------------------';
		PRINT 'Loading Enrichment Tables';
		PRINT '------------------------------------------------';

		-- ext_weather_consolidated
		-- Transformations:
		--   - Trim city names
		--   - No other cleaning required — source already clean
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.ext_weather_consolidated';
		TRUNCATE TABLE silver.ext_weather_consolidated;
		PRINT '>> Inserting Data Into: silver.ext_weather_consolidated';
		INSERT INTO silver.ext_weather_consolidated (
			city_name,
			weather_date,
			temp_max_c,
			temp_min_c,
			precipitation_mm,
			windspeed_max_kmh,
			dwh_create_date
		)
		SELECT
			TRIM(city_name)							AS city_name,
			weather_date,
			temp_max_c,
			temp_min_c,
			precipitation_mm,
			windspeed_max_kmh,
			GETDATE()								AS dwh_create_date
		FROM bronze.ext_weather_consolidated;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- ext_dexbzus
		-- Transformations:
		--   - Convert observation_date from NVARCHAR DD/MM/YYYY to DATE
		--   - Generate complete date spine from min to max date
		--   - Forward fill null rates for weekends and public holidays
		--   - Flag forward filled rows with is_forward_filled = 1
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.ext_dexbzus';
		TRUNCATE TABLE silver.ext_dexbzus;
		PRINT '>> Inserting Data Into: silver.ext_dexbzus';
		--DECLARE @fx_min_date DATE, @fx_max_date DATE;
		SET @fx_min_date = (SELECT MIN(CONVERT(DATE, observation_date, 103)) FROM bronze.ext_dexbzus);
		SET @fx_max_date = (SELECT MAX(CONVERT(DATE, observation_date, 103)) FROM bronze.ext_dexbzus);

		WITH date_spine AS (
			SELECT @fx_min_date AS dt
			UNION ALL
			SELECT DATEADD(DAY, 1, dt)
			FROM date_spine
			WHERE dt < @fx_max_date
		),
		rates AS (
			SELECT
				CONVERT(DATE, observation_date, 103) AS observation_date,
				CASE
					WHEN DEXBZUS IS NULL OR DEXBZUS = '' THEN NULL
					ELSE CAST(DEXBZUS AS DECIMAL(10,4))
				END										AS brl_usd_rate
			FROM bronze.ext_dexbzus
		),
		joined AS (
    SELECT
        d.dt                                    AS observation_date,
        r.brl_usd_rate,
        CASE
            WHEN r.brl_usd_rate IS NULL THEN 1
            ELSE 0
        END                                     AS is_forward_filled
    FROM date_spine d
    LEFT JOIN rates r ON d.dt = r.observation_date
		),
		grouped AS (
			SELECT
				observation_date,
				brl_usd_rate,
				is_forward_filled,
				COUNT(brl_usd_rate) OVER (
					ORDER BY observation_date
					ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
				)                                       AS grp
			FROM joined
		)
		INSERT INTO silver.ext_dexbzus (
			observation_date,
			brl_usd_rate,
			is_forward_filled,
			dwh_create_date
		)
		SELECT
			observation_date,
			MAX(brl_usd_rate) OVER (
				PARTITION BY grp
				ORDER BY observation_date
				ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
			)                                           AS brl_usd_rate,
			is_forward_filled,
			GETDATE()                                   AS dwh_create_date
		FROM grouped

		OPTION (MAXRECURSION 1200);
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- ext_macro_factors
		-- Transformations:
		--   - Cast year from INT to SMALLINT
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.ext_macro_factors';
		TRUNCATE TABLE silver.ext_macro_factors;
		PRINT '>> Inserting Data Into: silver.ext_macro_factors';
		INSERT INTO silver.ext_macro_factors (
			year,
			gdp_usd,
			inflation_pct,
			unemployment_pct,
			gdp_capita_usd,
			dwh_create_date
		)
		SELECT
			CAST(year AS SMALLINT)					AS year,
			gdp_usd,
			inflation_pct,
			unemployment_pct,
			gdp_capita_usd,
			GETDATE()								AS dwh_create_date
		FROM bronze.ext_macro_factors;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- ext_muncipal_population_est
		-- Transformations:
		--   - Uppercase state codes
		--   - Strip footnote references from population e.g. 43.935(2) -> 43935
		--   - Remove thousands separators (both . and ,) and quotes
		--   - Cast population to INT
		--   - City name encoding corruption stored as-is — normalised in gold
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.ext_muncipal_population_est';
		TRUNCATE TABLE silver.ext_muncipal_population_est;
		PRINT '>> Inserting Data Into: silver.ext_muncipal_population_est';
		INSERT INTO silver.ext_muncipal_population_est (
			uf,
			cod_uf,
			cod_munic,
			nome_municipio,
			populacao_estimada,
			dwh_create_date
		)
		SELECT
			UPPER(TRIM(uf))							AS uf,
			cod_uf,
			TRIM(cod_munic)							AS cod_munic,
			TRIM(nome_municipio)					AS nome_municipio,
			CAST(
				REPLACE(
					REPLACE(
						REPLACE(
							REPLACE(
								LEFT(
									TRIM(populacao_estimada),
									CHARINDEX('(', TRIM(populacao_estimada) + '(') - 1
								),
							'"', ''),
						',', ''),
					'.', ''),
				' ', '')
			AS INT)									AS populacao_estimada,
			GETDATE()								AS dwh_create_date
		FROM bronze.ext_muncipal_population_est;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- ext_brazil_holidays
		-- Transformations:
		--   - Convert date from NVARCHAR DD/MM/YYYY to DATE
		--   - Convert fixed and global from TRUE/FALSE strings to BIT
		--   - Rename columns to snake_case
		--   - Drop launchYear, counties, counties_0 — all null or irrelevant
		--   - Encoding corruption in local_name stored as-is
		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: silver.ext_brazil_holidays';
		TRUNCATE TABLE silver.ext_brazil_holidays;
		PRINT '>> Inserting Data Into: silver.ext_brazil_holidays';
		INSERT INTO silver.ext_brazil_holidays (
			holiday_date,
			local_name,
			name,
			country_code,
			is_fixed,
			is_global,
			holiday_type,
			holiday_type_2,
			dwh_create_date
		)
		SELECT
			CONVERT(DATE, date, 103)							AS holiday_date,
			TRIM(localName)										AS local_name,
			TRIM(name)											AS name,
			TRIM(countryCode)									AS country_code,
			CASE WHEN TRIM(fixed)  = 'TRUE' THEN 1 ELSE 0 END	AS is_fixed,
			CASE WHEN TRIM(global) = 'TRUE' THEN 1 ELSE 0 END	AS is_global,
			TRIM(types_0)										AS holiday_type,
			TRIM(types_1)										AS holiday_type_2,
			GETDATE()											AS dwh_create_date
		FROM bronze.ext_brazil_holidays;
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @batch_end_time = GETDATE();
		PRINT '================================================';
		PRINT 'Loading Silver Layer is Completed';
		PRINT '   - Total Load Duration: ' + CAST(DATEDIFF(SECOND, @batch_start_time, @batch_end_time) AS NVARCHAR) + ' seconds';
		PRINT '================================================';

	END TRY
	BEGIN CATCH
		PRINT '================================================';
		PRINT 'ERROR OCCURED DURING LOADING SILVER LAYER';
		PRINT 'Error Message : ' + ERROR_MESSAGE();
		PRINT 'Error Number  : ' + CAST(ERROR_NUMBER() AS NVARCHAR);
		PRINT 'Error State   : ' + CAST(ERROR_STATE()  AS NVARCHAR);
		PRINT '================================================';
	END CATCH
END

--Exec silver.load_silver;