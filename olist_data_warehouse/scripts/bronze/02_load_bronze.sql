/*
	Loads all bronze tables from the CSV files.
	EXEC bronze.load_bronze @data_path = 'C:\...\olist_data_warehouse\datasets\';
*/

USE Olist_DWP;
GO

CREATE OR ALTER PROCEDURE bronze.load_bronze
	@data_path NVARCHAR(400)
AS
BEGIN
	SET NOCOUNT ON;

	IF RIGHT(@data_path, 1) <> '\' SET @data_path += '\';

	-- reviews, translation and enrichment files use CRLF, the rest LF
	DECLARE @files TABLE (id INT, table_name NVARCHAR(128), file_name NVARCHAR(200), row_end VARCHAR(10));
	INSERT INTO @files VALUES
		(1,  'bronze.crm_olist_customers_dataset',           'core\crm\olist_customers_dataset.csv',           '0x0a'),
		(2,  'bronze.crm_olist_geolocation_dataset',         'core\crm\olist_geolocation_dataset.csv',         '0x0a'),
		(3,  'bronze.crm_olist_sellers_dataset',             'core\crm\olist_sellers_dataset.csv',             '0x0a'),
		(4,  'bronze.erp_olist_order_items_dataset',         'core\erp\olist_order_items_dataset.csv',         '0x0a'),
		(5,  'bronze.erp_olist_products_dataset',            'core\erp\olist_products_dataset.csv',            '0x0a'),
		(6,  'bronze.erp_product_category_name_translation', 'core\erp\product_category_name_translation.csv', '0x0d0a'),
		(7,  'bronze.oms_olist_orders_dataset',              'core\oms\olist_orders_dataset.csv',              '0x0a'),
		(8,  'bronze.oms_olist_orders_reviews_dataset',      'core\oms\olist_order_reviews_dataset.csv',       '0x0d0a'),
		(9,  'bronze.oms_olist_order_payments_dataset',      'core\oms\olist_order_payments_dataset.csv',      '0x0a'),
		(10, 'bronze.ext_brazil_holidays',                   'enrichment\brazil_holidays.csv',                 '0x0d0a'),
		(11, 'bronze.ext_dexbzus',                           'enrichment\dexbzus.csv',                         '0x0d0a'),
		(12, 'bronze.ext_macro_factors',                     'enrichment\macro_factors.csv',                   '0x0d0a'),
		(13, 'bronze.ext_municipal_population_est',          'enrichment\municipal_population_est.csv',        '0x0d0a'),
		(14, 'bronze.ext_weather_consolidated',              'enrichment\weather_consolidated.csv',            '0x0d0a');

	DECLARE @id INT = 1, @table NVARCHAR(128), @file NVARCHAR(200), @row_end VARCHAR(10);
	DECLARE @sql NVARCHAR(MAX), @rows INT, @start DATETIME2 = SYSDATETIME();

	BEGIN TRY
		WHILE @id <= (SELECT MAX(id) FROM @files)
		BEGIN
			SELECT @table = table_name, @file = file_name, @row_end = row_end FROM @files WHERE id = @id;

			SET @sql = N'
				TRUNCATE TABLE ' + @table + N';
				BULK INSERT ' + @table + N' FROM ''' + @data_path + @file + N'''
				WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', ROWTERMINATOR = ''' + @row_end + N''', CODEPAGE = ''65001'', TABLOCK);
				SELECT @rows = COUNT(*) FROM ' + @table + N';';

			EXEC sp_executesql @sql, N'@rows INT OUTPUT', @rows OUTPUT;
			PRINT @table + ': ' + FORMAT(@rows, 'N0') + ' rows';

			SET @id += 1;
		END

		PRINT 'Bronze loaded in ' + CAST(DATEDIFF(SECOND, @start, SYSDATETIME()) AS VARCHAR(10)) + 's';
	END TRY
	BEGIN CATCH
		PRINT 'Bronze load failed on ' + @table;
		THROW;
	END CATCH
END;
GO
