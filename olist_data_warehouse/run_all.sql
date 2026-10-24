/*
	Builds the whole warehouse from scratch: database, bronze, silver, gold,
	then runs the data quality checks.

	1. Set repo_path below to where this folder lives on your machine (no spaces in the path).
	2. In SSMS turn on Query > SQLCMD Mode.
	3. Press F5.
*/

:setvar repo_path C:\repos\Projects\olist_data_warehouse
:on error exit

:r $(repo_path)\scripts\00_init_database.sql

:r $(repo_path)\scripts\bronze\01_ddl_bronze.sql
:r $(repo_path)\scripts\bronze\02_load_bronze.sql
:r $(repo_path)\scripts\silver\03_ddl_silver.sql
:r $(repo_path)\scripts\silver\04_load_silver.sql
:r $(repo_path)\scripts\gold\05_ddl_gold.sql
:r $(repo_path)\scripts\gold\06_load_gold.sql

USE Olist_DWP;
GO

EXEC bronze.load_bronze @data_path = '$(repo_path)\datasets\';
GO
EXEC silver.load_silver;
GO
EXEC gold.load_fact_orders;
GO

:r $(repo_path)\tests\data_quality_checks.sql
