import pytest

from askit.guardrails import GuardrailError, check_sql

ALLOWED = {"chatbot.v_orders_full", "chatbot.v_seller_summary", "chatbot.v_monthly_trends"}


def check(sql, dialect="tsql"):
    return check_sql(sql, dialect, ALLOWED)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM chatbot.v_orders_full",
        "SELECT TOP 10 seller_id, total_revenue_brl FROM chatbot.v_seller_summary ORDER BY total_revenue_brl DESC;",
        "SELECT o.order_id, s.seller_tier FROM chatbot.v_orders_full o JOIN chatbot.v_seller_summary s ON s.seller_id = o.seller_id",
        "WITH ranked AS (SELECT seller_id, ROW_NUMBER() OVER (ORDER BY total_revenue_brl DESC) AS rn FROM chatbot.v_seller_summary) SELECT * FROM ranked WHERE rn <= 5",
        "SELECT year FROM chatbot.v_monthly_trends UNION ALL SELECT order_year FROM chatbot.v_orders_full",
        "SELECT * FROM chatbot.v_orders_full WHERE seller_id IN (SELECT seller_id FROM chatbot.v_seller_summary WHERE seller_tier = 'Gold')",
        "select count(*) from CHATBOT.V_ORDERS_FULL",
        "-- top sellers\nSELECT seller_id FROM chatbot.v_seller_summary",
    ],
)
def test_allows_read_only_queries(sql):
    assert check(sql).tables


def test_reports_tables_used():
    result = check("SELECT * FROM chatbot.v_orders_full o JOIN chatbot.v_seller_summary s ON s.seller_id = o.seller_id")
    assert result.tables == ["chatbot.v_orders_full", "chatbot.v_seller_summary"]


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("DROP TABLE chatbot.v_orders_full", "Only SELECT"),
        ("DELETE FROM chatbot.v_orders_full", "Only SELECT"),
        ("UPDATE chatbot.v_seller_summary SET seller_tier = 'Gold'", "Only SELECT"),
        ("INSERT INTO chatbot.v_orders_full (order_id) VALUES ('x')", "Only SELECT"),
        ("WITH r AS (SELECT 1 AS a) INSERT INTO chatbot.v_orders_full SELECT * FROM r", "Only SELECT"),
        ("ALTER VIEW chatbot.v_orders_full AS SELECT 1 AS a", "Only SELECT"),
        ("CREATE TABLE chatbot.t (a INT)", "Only SELECT"),
        ("EXEC sp_who", "Only SELECT"),
        ("DECLARE @x INT = 1", "Only SELECT"),
        ("SELECT * INTO chatbot.copy FROM chatbot.v_orders_full", "SELECT INTO"),
    ],
)
def test_blocks_writes_and_other_statements(sql, reason):
    with pytest.raises(GuardrailError, match=reason):
        check(sql)


def test_blocks_multiple_statements():
    with pytest.raises(GuardrailError, match="one statement"):
        check("SELECT COUNT(*) FROM chatbot.v_orders_full; DROP TABLE chatbot.v_orders_full")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT TOP 5 * FROM gold.fact_orders",
        "SELECT * FROM silver.oms_olist_orders_dataset",
        "SELECT name FROM sys.objects",
        "SELECT * FROM sys.dm_exec_sessions",
        "SELECT * FROM INFORMATION_SCHEMA.TABLES",
        "SELECT * FROM v_orders_full",
        "WITH x AS (SELECT * FROM gold.fact_orders) SELECT * FROM x",
        "SELECT * FROM chatbot.v_orders_full WHERE order_id IN (SELECT order_id FROM gold.fact_orders)",
    ],
)
def test_blocks_tables_outside_the_allow_list(sql):
    with pytest.raises(GuardrailError, match="not one of the tables"):
        check(sql)


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("SELECT * FROM Olist_DWP.chatbot.v_orders_full", "Cross-database"),
        ("SELECT * FROM srv.Olist_DWP.chatbot.v_orders_full", "Cross-database"),
        ("SELECT * FROM OPENROWSET('SQLNCLI', 'Server=x;Trusted_Connection=yes', 'SELECT 1') AS a", "named tables"),
        ("SELECT * FROM OPENQUERY(srv, 'SELECT 1')", "named tables"),
    ],
)
def test_blocks_other_databases_and_remote_sources(sql, reason):
    with pytest.raises(GuardrailError, match=reason):
        check(sql)


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("", "empty"),
        ("   ;  ", "empty"),
        ("SELEC order_id FORM chatbot.v_orders_full", "could not be parsed"),
        ('SELECT "state_revenue FROM chatbot.v_orders_full', "could not be parsed"),
        ("SELECT 1", "any allowed table"),
    ],
)
def test_rejects_empty_or_invalid_queries(sql, reason):
    with pytest.raises(GuardrailError, match=reason):
        check(sql)


def test_cte_named_like_a_blocked_table_is_fine():
    assert check("WITH fact_orders AS (SELECT order_id FROM chatbot.v_orders_full) SELECT * FROM fact_orders").tables == [
        "chatbot.v_orders_full"
    ]


def test_sqlite_dialect():
    allowed = {"v_orders_full"}
    assert check_sql("SELECT COUNT(*) FROM v_orders_full LIMIT 5", "sqlite", allowed).tables == ["v_orders_full"]
    with pytest.raises(GuardrailError, match="not one of the tables"):
        check_sql("SELECT name FROM sqlite_master", "sqlite", allowed)
    with pytest.raises(GuardrailError, match="Only SELECT"):
        check_sql("ATTACH DATABASE 'other.db' AS other", "sqlite", allowed)
