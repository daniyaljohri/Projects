import io
import re
from datetime import date, datetime, timezone
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from askit.db import QueryResult
from askit.llm import PLAIN_NUMBER_COLUMNS

HEADER_FILL = PatternFill("solid", start_color="1D9E75")
STRIPE_FILL = PatternFill("solid", start_color="F5F5F5")
HEADER_FONT = Font(bold=True, color="FFFFFF")
MAX_COLUMN_WIDTH = 50

UNITS = {"brl": "(BRL)", "usd": "(USD)", "pct": "(%)", "g": "(g)", "cm3": "(cm³)", "kmh": "(km/h)", "c": "(°C)", "mm": "(mm)"}
WORDS = {"id": "ID", "avg": "Avg", "qty": "Qty", "usd": "USD", "brl": "BRL"}
PERCENT_COLUMN = re.compile(r"(_pct|_rate|percent|_share)$", re.IGNORECASE)


def header_label(column: str) -> str:
    """total_revenue_brl -> Total Revenue (BRL), late_delivery_rate_pct -> Late Delivery Rate (%)"""
    parts = column.lower().split("_")
    unit = UNITS.get(parts[-1]) if len(parts) > 1 else None
    if unit:
        parts = parts[:-1]
    words = [WORDS.get(p, p.capitalize()) for p in parts if p]
    return " ".join(words + ([unit] if unit else []))


def number_format(column: str, values: list) -> str | None:
    sample = next((v for v in values if v is not None), None)
    if isinstance(sample, datetime):
        return "yyyy-mm-dd hh:mm"
    if isinstance(sample, date):
        return "yyyy-mm-dd"
    if isinstance(sample, bool) or not isinstance(sample, (int, float, Decimal)):
        return None
    if PLAIN_NUMBER_COLUMNS.search(column):
        return "0"
    # percentages in the views are already 0-100, so show a literal % instead of multiplying by 100
    if PERCENT_COLUMN.search(column):
        return '0.0"%"'
    if all(isinstance(v, int) or (isinstance(v, (float, Decimal)) and float(v).is_integer()) for v in values if v is not None):
        return "#,##0"
    return "#,##0.00"


def _cell_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime) and value.tzinfo:
        return value.replace(tzinfo=None)
    return value


def build_workbook(result: QueryResult, question: str, sql: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"

    for col, column in enumerate(result.columns, start=1):
        cell = sheet.cell(row=1, column=col, value=header_label(column))
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_number, row in enumerate(result.rows, start=2):
        for col, column in enumerate(result.columns, start=1):
            cell = sheet.cell(row=row_number, column=col, value=_cell_value(row[column]))
            if row_number % 2 == 1:
                cell.fill = STRIPE_FILL

    for col, column in enumerate(result.columns, start=1):
        values = [row[column] for row in result.rows]
        fmt = number_format(column, values)
        letter = get_column_letter(col)
        if fmt:
            for cell in sheet[letter][1:]:
                cell.number_format = fmt
        longest = max([len(header_label(column))] + [len(str(v)) for v in values[:500] if v is not None])
        sheet.column_dimensions[letter].width = min(longest + 3, MAX_COLUMN_WIDTH)

    sheet.freeze_panes = "A2"
    if result.rows:
        sheet.auto_filter.ref = sheet.dimensions

    # a second sheet records where the numbers came from
    about = workbook.create_sheet("Query")
    details = [
        ("Question", question),
        ("Rows", result.row_count),
        ("Note", "Results were cut off at the row limit." if result.truncated else ""),
        ("Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        ("SQL", sql),
    ]
    for row_number, (label, value) in enumerate(details, start=1):
        about.cell(row=row_number, column=1, value=label).font = Font(bold=True)
        about.cell(row=row_number, column=2, value=value).alignment = Alignment(wrap_text=True, vertical="top")
    about.column_dimensions["A"].width = 12
    about.column_dimensions["B"].width = 100

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def filename_for(question: str) -> str:
    """'Top 10 sellers by revenue?' -> top_10_sellers_by_revenue.xlsx"""
    slug = re.sub(r"[^a-z0-9]+", "_", question.lower()).strip("_")[:60].rstrip("_")
    return f"{slug or 'askit_results'}.xlsx"
