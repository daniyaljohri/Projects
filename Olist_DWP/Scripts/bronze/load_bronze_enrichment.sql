-- ============================================================
-- Stored Procedure : bronze.load_bronze
-- Layer            : Bronze
-- Description      : Truncates and reloads all bronze tables.
--
-- Loading Strategy (Hybrid):
--   Enrichment tables (ext_) : Loaded here via BULK INSERT
--   Core Olist tables        : Loaded via Python (load_bronze.py)
--                              due to RFC 4180 quoted fields with
--                              embedded commas that BULK INSERT
--                              cannot parse reliably.
--
-- Usage            : EXEC bronze.load_bronze
-- ============================================================
CREATE OR ALTER PROCEDURE bronze.load_bronze AS
BEGIN
	DECLARE @start_time DATETIME, @end_time DATETIME, @batch_start_time DATETIME, @batch_end_time DATETIME;
	BEGIN TRY
		SET @batch_start_time = GETDATE();
		PRINT '================================================';
		PRINT 'Loading Bronze Layer — Enrichment Tables';
		PRINT '================================================';

		-- --------------------------------------------------------
		-- ENRICHMENT TABLES
		-- --------------------------------------------------------
		PRINT '------------------------------------------------';
		PRINT 'Loading Enrichment Tables';
		PRINT '------------------------------------------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.ext_brazil_holidays';
		TRUNCATE TABLE bronze.ext_brazil_holidays;
		PRINT '>> Inserting Data Into: bronze.ext_brazil_holidays';
		BULK INSERT bronze.ext_brazil_holidays
		FROM 'D:\Projects\Data_Warehouse_Project\Datasets\Enrichment\brazil_holidays.csv'
		WITH (
			FIRSTROW = 2,
			FIELDTERMINATOR = ',',
			TABLOCK
		);
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.ext_dexbzus';
		TRUNCATE TABLE bronze.ext_dexbzus;
		PRINT '>> Inserting Data Into: bronze.ext_dexbzus';
		BULK INSERT bronze.ext_dexbzus
		FROM 'D:\Projects\Data_Warehouse_Project\Datasets\Enrichment\DEXBZUS.csv'
		WITH (
			FIRSTROW = 2,
			FIELDTERMINATOR = ',',
			TABLOCK
		);
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.ext_macro_factors';
		TRUNCATE TABLE bronze.ext_macro_factors;
		PRINT '>> Inserting Data Into: bronze.ext_macro_factors';
		BULK INSERT bronze.ext_macro_factors
		FROM 'D:\Projects\Data_Warehouse_Project\Datasets\Enrichment\macro_factors.csv'
		WITH (
			FIRSTROW = 2,
			FIELDTERMINATOR = ',',
			TABLOCK
		);
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.ext_muncipal_population_est';
		TRUNCATE TABLE bronze.ext_muncipal_population_est;

		BULK INSERT bronze.ext_muncipal_population_est
		FROM 'D:\Projects\Data_Warehouse_Project\Datasets\Enrichment\population_fixed.csv'
		WITH (
			FIRSTROW = 2,
			FIELDTERMINATOR = ',',
			CODEPAGE = '65001',
			TABLOCK
		);
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		SET @start_time = GETDATE();
		PRINT '>> Truncating Table: bronze.ext_weather_consolidated';
		TRUNCATE TABLE bronze.ext_weather_consolidated;
		PRINT '>> Inserting Data Into: bronze.ext_weather_consolidated';
		BULK INSERT bronze.ext_weather_consolidated
		FROM 'D:\Projects\Data_Warehouse_Project\Datasets\Enrichment\weather_consolidated.csv'
		WITH (
			FIRSTROW = 2,
			FIELDTERMINATOR = ',',
			TABLOCK
		);
		SET @end_time = GETDATE();
		PRINT '>> Load Duration: ' + CAST(DATEDIFF(SECOND, @start_time, @end_time) AS NVARCHAR) + ' seconds';
		PRINT '>> -------------';

		-- --------------------------------------------------------
		-- NOTE: Core Olist tables loaded via Python (load_bronze.py)
		-- due to RFC 4180 quoted fields with embedded commas.
		--
		--   bronze.crm_olist_customers_dataset
		--   bronze.crm_olist_geolocation_dataset
		--   bronze.crm_olist_sellers_dataset
		--   bronze.erp_olist_order_items_dataset
		--   bronze.erp_olist_products_dataset
		--   bronze.erp_product_category_name_translation
		--   bronze.oms_olist_orders_dataset
		--   bronze.oms_olist_orders_reviews_dataset
		--   bronze.oms_olist_order_payments_dataset
		-- --------------------------------------------------------

		SET @batch_end_time = GETDATE();
		PRINT '================================================';
		PRINT 'Bronze Layer — Enrichment Load Complete';
		PRINT '   - Tables Loaded (BULK INSERT) : 5';
		PRINT '   - Tables via Python           : 9';
		PRINT '   - Total Load Duration: ' + CAST(DATEDIFF(SECOND, @batch_start_time, @batch_end_time) AS NVARCHAR) + ' seconds';
		PRINT '================================================';

	END TRY
	BEGIN CATCH
		PRINT '================================================';
		PRINT 'ERROR OCCURED DURING LOADING BRONZE LAYER';
		PRINT 'Error Message : ' + ERROR_MESSAGE();
		PRINT 'Error Number  : ' + CAST(ERROR_NUMBER() AS NVARCHAR);
		PRINT 'Error State   : ' + CAST(ERROR_STATE()  AS NVARCHAR);
		PRINT '================================================';
	END CATCH
END