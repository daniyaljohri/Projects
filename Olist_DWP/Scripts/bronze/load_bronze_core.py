"""
===============================================================================
Script       : load_bronze.py
Layer        : Bronze
Description  : Loads the 9 core Olist tables into bronze via pyodbc.

Loading Strategy (Hybrid):
  - 9 core Olist tables : Loaded here via Python
    These CSVs contain RFC 4180 quoted fields with embedded commas
    that BULK INSERT cannot parse with a simple field terminator.
  - 5 enrichment tables : Loaded via BULK INSERT in SQL Server
    (see bronze.load_bronze stored procedure)

Pre-processing applied:
  - NaN/NaT/empty → Python None (SQL NULL) via cell-level conversion
  - Fully blank rows removed (trailing rows from CSV exports)
  - No business logic — that belongs in the silver layer

Usage        : python load_bronze.py
===============================================================================
"""

import pyodbc
import pandas as pd
import numpy as np
import time
from datetime import datetime

# ── Connection ────────────────────────────────────────────────────────────────

SERVER   = r'LAPTOP-S6C1L72A\SQLEXPRESS'
DATABASE = 'Olist_DWP'

conn = pyodbc.connect(
    f'DRIVER={{SQL Server}};'
    f'SERVER={SERVER};'
    f'DATABASE={DATABASE};'
    f'Trusted_Connection=yes;'
    f'autocommit=False;'
)
cursor                  = conn.cursor()
cursor.fast_executemany = True

# ── File paths ────────────────────────────────────────────────────────────────

CRM = r'D:\Projects\Data_Warehouse_Project\Datasets\Core\CRM'
ERP = r'D:\Projects\Data_Warehouse_Project\Datasets\Core\ERP'
OMS = r'D:\Projects\Data_Warehouse_Project\Datasets\Core\OMS'

# ── Table definitions ─────────────────────────────────────────────────────────
# Only the 9 core Olist tables — enrichment handled by BULK INSERT

TABLES = [
    # CRM
    ('bronze.crm_olist_customers_dataset',            CRM + r'\olist_customers_dataset.csv',             5),
    ('bronze.crm_olist_geolocation_dataset',          CRM + r'\olist_geolocation_dataset.csv',           5),
    ('bronze.crm_olist_sellers_dataset',              CRM + r'\olist_sellers_dataset.csv',               4),
    # ERP
    ('bronze.erp_olist_order_items_dataset',          ERP + r'\olist_order_items_dataset.csv',           7),
    ('bronze.erp_olist_products_dataset',             ERP + r'\olist_products_dataset.csv',              9),
    ('bronze.erp_product_category_name_translation',  ERP + r'\product_category_name_translation.csv',   2),
    # OMS
    ('bronze.oms_olist_orders_dataset',               OMS + r'\olist_orders_dataset.csv',                8),
    ('bronze.oms_olist_orders_reviews_dataset',       OMS + r'\olist_order_reviews_dataset.csv',         7),
    ('bronze.oms_olist_order_payments_dataset',       OMS + r'\olist_order_payments_dataset.csv',        5),
]

# ── Pre-processing ────────────────────────────────────────────────────────────

def preprocess(df):
    """
    Minimal pre-processing before insert.
    Only removes fully blank trailing rows.
    No business logic — that belongs in the silver layer.
    """
    df = df.dropna(how='all')
    return df


def to_insert_rows(df):
    """
    Convert DataFrame to list of lists with proper None values.
    Checks every cell individually:
      - numpy NaN, pandas NaT, float('nan'), string 'nan', empty → None
      - Everything else → Python str
    This is the only reliable way to pass NULLs through pyodbc
    regardless of pandas version or dtype quirks.
    """
    rows = []
    for row in df.itertuples(index=False, name=None):
        cleaned = []
        for val in row:
            if val is None:
                cleaned.append(None)
            elif isinstance(val, float) and np.isnan(val):
                cleaned.append(None)
            elif str(val).strip().lower() == 'nan':
                cleaned.append(None)
            elif str(val).strip() == '':
                cleaned.append(None)
            else:
                cleaned.append(str(val))
        rows.append(cleaned)
    return rows

# ── Loader ────────────────────────────────────────────────────────────────────

def load_table(table_name, file_path, num_cols):
    # Let pandas detect NaN naturally — do NOT use keep_default_na=False
    df   = pd.read_csv(file_path, dtype=str)
    df   = preprocess(df)
    rows = to_insert_rows(df)
    sql  = f"INSERT INTO {table_name} VALUES ({','.join(['?'] * num_cols)})"

    cursor.execute(f"TRUNCATE TABLE {table_name}")

    try:
        # Fast path — single batch
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        conn.commit()

    except Exception:
        # Slow path — row by row to identify exact failing row
        conn.rollback()
        cursor.fast_executemany = False
        for i, row in enumerate(rows):
            try:
                cursor.execute(sql, row)
            except Exception as e:
                print(f"   ROW {i+2} FAILED : {row}")
                print(f"   ERROR          : {e}")
                raise
        conn.commit()

    return len(rows)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=' * 60)
    print('  Loading Bronze Layer — Core Olist Tables (Python)')
    print(f'  Started : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)

    batch_start = time.time()
    failed      = []

    for table_name, file_path, num_cols in TABLES:
        print(f'\n>> Loading : {table_name}')
        start = time.time()
        try:
            rows     = load_table(table_name, file_path, num_cols)
            duration = round(time.time() - start, 2)
            print(f'   Rows    : {rows:,}')
            print(f'   Duration: {duration}s')
        except Exception as e:
            print(f'   ERROR   : {e}')
            failed.append(table_name)
            conn.rollback()

    batch_duration = round(time.time() - batch_start, 2)

    print('\n' + '=' * 60)
    print('  Bronze Layer — Core Olist Load Complete')
    print(f'  Total Duration : {batch_duration}s')
    print(f'  Tables Loaded  : {len(TABLES) - len(failed)}/{len(TABLES)}')
    if failed:
        print(f'  Failed Tables  : {failed}')
    else:
        print('  All 9 tables loaded successfully!')
    print('  Note: 5 enrichment tables loaded via BULK INSERT')
    print('        (run EXEC bronze.load_bronze in SSMS)')
    print('=' * 60)

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
