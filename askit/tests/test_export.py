from datetime import datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook

from askit.db import QueryResult
from askit.export import build_workbook, filename_for, header_label, number_format


def test_header_labels():
    assert header_label("total_revenue_brl") == "Total Revenue (BRL)"
    assert header_label("late_delivery_rate_pct") == "Late Delivery Rate (%)"
    assert header_label("customer_unique_id") == "Customer Unique ID"
    assert header_label("avg_weight_g") == "Avg Weight (g)"
    assert header_label("year") == "Year"


def test_number_formats_follow_the_values():
    assert number_format("avg_review_score", [4.13, 3.9]) == "#,##0.00"
    assert number_format("total_orders", [312, 44579]) == "#,##0"
    assert number_format("late_delivery_rate_pct", [12.1]) == '0.0"%"'
    assert number_format("order_year", [2016]) == "0"
    assert number_format("seller_state", ["SP"]) is None
    assert number_format("last_order_date", [datetime(2018, 1, 1)]) == "yyyy-mm-dd hh:mm"


def test_workbook_has_results_and_query_sheets():
    result = QueryResult(
        columns=["seller_id", "total_revenue_brl", "avg_review_score"],
        rows=[
            {"seller_id": "a", "total_revenue_brl": Decimal("249640.70"), "avg_review_score": 4.133},
            {"seller_id": "b", "total_revenue_brl": Decimal("239536.44"), "avg_review_score": None},
        ],
        truncated=False,
    )
    workbook = load_workbook(BytesIO(build_workbook(result, "Top sellers?", "SELECT 1")))

    sheet = workbook["Results"]
    assert [c.value for c in sheet[1]] == ["Seller ID", "Total Revenue (BRL)", "Avg Review Score"]
    assert sheet["B2"].value == 249640.70
    assert sheet["B2"].number_format == "#,##0.00"
    assert sheet["C2"].value == 4.133
    assert sheet.freeze_panes == "A2"

    query = workbook["Query"]
    assert query["B1"].value == "Top sellers?"
    assert query["B5"].value == "SELECT 1"


def test_filename_from_question():
    assert filename_for("Who are the top 10 sellers by revenue?") == "who_are_the_top_10_sellers_by_revenue.xlsx"
    assert filename_for("???") == "askit_results.xlsx"
