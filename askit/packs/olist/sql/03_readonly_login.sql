/*
	Read-only login for Askit: SELECT on chatbot, nothing else.
	The password is generated on first run and printed once.
*/

USE master;
GO

IF SERVERPROPERTY('IsIntegratedSecurityOnly') = 1
	THROW 50020, 'SQL Server authentication is off. Turn on mixed mode and restart the service.', 1;

IF DB_ID('Olist_DWP') IS NULL OR NOT EXISTS (SELECT 1 FROM Olist_DWP.sys.schemas WHERE name = 'chatbot')
	THROW 50021, 'Run 01_chatbot_schema.sql and 02_chatbot_views.sql first.', 1;

IF SUSER_ID('askit_reader') IS NULL
BEGIN
	DECLARE @password NVARCHAR(64) = CONVERT(NVARCHAR(36), NEWID()) + N'a';
	DECLARE @sql NVARCHAR(500) =
		N'CREATE LOGIN askit_reader WITH PASSWORD = ' + QUOTENAME(@password, '''')
		+ N', DEFAULT_DATABASE = Olist_DWP, CHECK_POLICY = ON, CHECK_EXPIRATION = OFF';
	EXEC (@sql);
	PRINT 'Created login askit_reader. Copy this password into .env:';
	PRINT @password;
END
ELSE
	PRINT 'Login askit_reader already exists';

-- one batch, so it stops on the first error
EXEC Olist_DWP.sys.sp_executesql N'
	IF USER_ID(''askit_reader'') IS NULL
		CREATE USER askit_reader FOR LOGIN askit_reader;

	GRANT SELECT ON SCHEMA::chatbot TO askit_reader;

	-- views still work through ownership chaining
	DENY SELECT ON SCHEMA::gold   TO askit_reader;
	DENY SELECT ON SCHEMA::silver TO askit_reader;
	DENY SELECT ON SCHEMA::bronze TO askit_reader;
';
PRINT 'askit_reader can SELECT from chatbot only';
GO

-- checks
USE Olist_DWP;
GO

DECLARE @rows INT;

EXECUTE AS USER = 'askit_reader';

DECLARE
	@read_chatbot  INT = HAS_PERMS_BY_NAME('chatbot', 'SCHEMA', 'SELECT'),
	@read_gold     INT = HAS_PERMS_BY_NAME('gold', 'SCHEMA', 'SELECT'),
	@read_silver   INT = HAS_PERMS_BY_NAME('silver', 'SCHEMA', 'SELECT'),
	@read_bronze   INT = HAS_PERMS_BY_NAME('bronze', 'SCHEMA', 'SELECT'),
	@write_chatbot INT = HAS_PERMS_BY_NAME('chatbot', 'SCHEMA', 'INSERT'),
	@alter_chatbot INT = HAS_PERMS_BY_NAME('chatbot', 'SCHEMA', 'ALTER'),
	@create_table  INT = HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE');

SELECT @rows = COUNT(*) FROM chatbot.v_monthly_trends;

REVERT;

IF @read_chatbot <> 1 OR @rows = 0
	THROW 50022, 'askit_reader cannot read the chatbot views.', 1;

IF @read_gold <> 0 OR @read_silver <> 0 OR @read_bronze <> 0
	THROW 50023, 'askit_reader can read gold, silver or bronze directly.', 1;

IF @write_chatbot <> 0 OR @alter_chatbot <> 0 OR @create_table <> 0
	THROW 50024, 'askit_reader has write or DDL permissions.', 1;

PRINT 'All login checks passed';

SELECT
	'chatbot' AS schema_name, @read_chatbot AS can_select, @write_chatbot AS can_insert, @alter_chatbot AS can_alter
UNION ALL SELECT 'gold',   @read_gold,   0, 0
UNION ALL SELECT 'silver', @read_silver, 0, 0
UNION ALL SELECT 'bronze', @read_bronze, 0, 0;
GO
