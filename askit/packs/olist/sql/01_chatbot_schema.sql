/*
	Creates the chatbot schema. Askit only reads from here.
*/

USE Olist_DWP;
GO

IF SCHEMA_ID('chatbot') IS NULL
BEGIN
	EXEC('CREATE SCHEMA chatbot AUTHORIZATION dbo');
	PRINT 'Created schema chatbot';
END
ELSE
	PRINT 'Schema chatbot already exists';
GO

IF SCHEMA_ID('chatbot') IS NULL
	THROW 50001, 'Schema chatbot was not created.', 1;
GO

SELECT
	s.name                    AS schema_name,
	USER_NAME(s.principal_id) AS owner
FROM sys.schemas s
WHERE s.name = 'chatbot';
GO
