/*
===============================================================================
Script   : 00_init_database.sql
Purpose  : Creates the Olist_DWP database and the bronze, silver and gold schemas.
Run      : First, once, in SSMS (connected to master).
Safe     : Re-runnable. Skips anything that already exists and drops nothing.
===============================================================================
*/

USE master;
GO

IF DB_ID('Olist_DWP') IS NULL
BEGIN
	CREATE DATABASE Olist_DWP;
	PRINT 'Created database Olist_DWP';
END
ELSE
	PRINT 'Database Olist_DWP already exists';
GO

USE Olist_DWP;
GO

IF SCHEMA_ID('bronze') IS NULL EXEC('CREATE SCHEMA bronze');
IF SCHEMA_ID('silver') IS NULL EXEC('CREATE SCHEMA silver');
IF SCHEMA_ID('gold')   IS NULL EXEC('CREATE SCHEMA gold');
GO

SELECT name AS schema_name
FROM sys.schemas
WHERE name IN ('bronze', 'silver', 'gold');
GO
