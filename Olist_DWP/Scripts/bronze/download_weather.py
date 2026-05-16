"""
Open-Meteo Historical Weather Downloader
Olist Data Warehouse - Bronze Layer Enrichment

Downloads daily weather data for 13 Brazilian cities (2016-2018)
and consolidates into a single CSV file: weather_consolidated.csv

Requirements:
    pip install requests pandas

Usage:
    python download_weather.py
"""

import requests
import pandas as pd
import time
from io import StringIO

OUTPUT_FILE = "weather_consolidated.csv"
START_DATE  = "2016-01-01"
END_DATE    = "2018-12-31"
DAILY_VARS  = "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max"
BASE_URL    = "https://archive-api.open-meteo.com/v1/archive"

CITIES = [
    {"city_name": "sao paulo",      "latitude": -23.5505, "longitude": -46.6333, "timezone": "America/Sao_Paulo"},
    {"city_name": "rio de janeiro", "latitude": -22.9068, "longitude": -43.1729, "timezone": "America/Sao_Paulo"},
    {"city_name": "belo horizonte", "latitude": -19.9167, "longitude": -43.9345, "timezone": "America/Sao_Paulo"},
    {"city_name": "brasilia",       "latitude": -15.7801, "longitude": -47.9292, "timezone": "America/Sao_Paulo"},
    {"city_name": "curitiba",       "latitude": -25.4278, "longitude": -49.2731, "timezone": "America/Sao_Paulo"},
    {"city_name": "porto alegre",   "latitude": -30.0346, "longitude": -51.2177, "timezone": "America/Sao_Paulo"},
    {"city_name": "salvador",       "latitude": -12.9714, "longitude": -38.5014, "timezone": "America/Bahia"},
    {"city_name": "fortaleza",      "latitude":  -3.7172, "longitude": -38.5433, "timezone": "America/Fortaleza"},
    {"city_name": "manaus",         "latitude":  -3.1190, "longitude": -60.0217, "timezone": "America/Manaus"},
    {"city_name": "recife",         "latitude":  -8.0539, "longitude": -34.8811, "timezone": "America/Recife"},
    {"city_name": "campinas",       "latitude": -22.9056, "longitude": -47.0608, "timezone": "America/Sao_Paulo"},
    {"city_name": "goiania",        "latitude": -16.6864, "longitude": -49.2643, "timezone": "America/Sao_Paulo"},
    {"city_name": "guarulhos",      "latitude": -23.4543, "longitude": -46.5338, "timezone": "America/Sao_Paulo"},
]

def download_city(city):
    params = {
        "latitude":   city["latitude"],
        "longitude":  city["longitude"],
        "start_date": START_DATE,
        "end_date":   END_DATE,
        "daily":      DAILY_VARS,
        "format":     "csv",
        "timezone":   city["timezone"],
    }
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        lines = response.text.splitlines()
        header_idx = next((i for i, line in enumerate(lines) if line.startswith("time")), None)
        if header_idx is None:
            print(f"  [ERROR] Could not find data header for {city['city_name']}")
            return None
        csv_content = "\n".join(lines[header_idx:])
        df = pd.read_csv(StringIO(csv_content))
        df.insert(0, "city_name", city["city_name"])
        df.rename(columns={
            "time":               "weather_date",
            "temperature_2m_max": "temp_max_c",
            "temperature_2m_min": "temp_min_c",
            "precipitation_sum":  "precipitation_mm",
            "windspeed_10m_max":  "windspeed_max_kmh",
        }, inplace=True)
        print(f"  [OK] {city['city_name']:20s} — {len(df)} rows")
        return df
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] {city['city_name']} — {e}")
        return None

def main():
    print(f"Downloading weather data for {len(CITIES)} cities...")
    all_frames = []
    failed = []
    for i, city in enumerate(CITIES, start=1):
        print(f"[{i:02d}/{len(CITIES)}] {city['city_name']}")
        df = download_city(city)
        if df is not None:
            all_frames.append(df)
        else:
            failed.append(city["city_name"])
        if i < len(CITIES):
            time.sleep(1)
    if not all_frames:
        print("No data downloaded. Check your internet connection.")
        return
    consolidated = pd.concat(all_frames, ignore_index=True)
    consolidated["weather_date"] = pd.to_datetime(consolidated["weather_date"]).dt.strftime("%Y-%m-%d")
    consolidated.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {OUTPUT_FILE}")
    print(f"Total rows: {len(consolidated):,}")
    if failed:
        print(f"Failed: {failed}")

if __name__ == "__main__":
    main()