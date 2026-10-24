# Data Sources

Where every dataset in this warehouse comes from, what it covers, and the terms it is used under.

The code in this repository is MIT licensed. The data is not covered by that licence; each dataset keeps its own terms, listed below.

## Core data: Olist (not included in this repo)

| Item | Detail |
|---|---|
| Dataset | Brazilian E-Commerce Public Dataset by Olist |
| Link | https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce |
| Coverage | About 100K orders, September 2016 to October 2018 |
| Files | 9 CSVs: orders, order items, customers, sellers, products, payments, reviews, geolocation, category translation |
| Licence | CC BY-NC-SA 4.0 |

The Olist files are about 120 MB, so they are not committed. Download them from Kaggle and place them as shown below. The folder is listed in `.gitignore`.

```
datasets/core/
├── crm/   olist_customers_dataset.csv, olist_geolocation_dataset.csv, olist_sellers_dataset.csv
├── erp/   olist_order_items_dataset.csv, olist_products_dataset.csv, product_category_name_translation.csv
└── oms/   olist_orders_dataset.csv, olist_order_payments_dataset.csv, olist_order_reviews_dataset.csv
```

## Enrichment data (snapshot included in `datasets/enrichment/`)

These files are small and committed as a snapshot so the warehouse always builds the same way, even if a source changes later.

| File | Source | What it holds | Coverage | Join key | Licence |
|---|---|---|---|---|---|
| `weather_consolidated.csv` | [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | Daily max/min temperature, rainfall, max wind speed for 13 Brazilian cities | 2016-01-01 to 2018-12-31 | Seller city + carrier dispatch date | [CC BY 4.0](https://open-meteo.com/en/licence) |
| `DEXBZUS.csv` | [FRED, series DEXBZUS](https://fred.stlouisfed.org/series/DEXBZUS) (source: Board of Governors of the Federal Reserve System, H.10) | Daily BRL per 1 USD exchange rate | 2015-12-01 to 2019-01-31 | Order purchase date | Public domain; cite FRED |
| `macro_factors.csv` | [World Bank, World Development Indicators](https://data.worldbank.org/country/brazil) | GDP (current US$), inflation (consumer prices, annual %), unemployment (% of labour force), GDP per capita (current US$) | 2015 to 2019, annual | Order year | [CC BY 4.0](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) |
| `muncipal_population_est.csv` | [IBGE, Estimativas da População 2020](https://www.ibge.gov.br/estatisticas/sociais/populacao/9103-estimativas-de-populacao.html) | Estimated population for all 5,570 Brazilian municipalities | 2020 estimate | State + city name | Brazilian open government data; cite IBGE |
| `brazil_holidays.csv` | [Nager.Date public holiday API](https://date.nager.at/) | National public holidays for Brazil | 2016 to 2018 | Order purchase date | [MIT](https://github.com/nager/Nager.Date) |

World Bank indicator codes: `NY.GDP.MKTP.CD`, `FP.CPI.TOTL.ZG`, `SL.UEM.TOTL.ZS`, `NY.GDP.PCAP.CD`.

## Known quirks in the source files

- **Holidays:** some Portuguese names are mis-encoded (for example `ConfraternizaÃ§Ã£o` instead of `Confraternização`). Kept as-is in bronze and handled downstream.
- **FRED:** no rows for weekends and US holidays. Gaps are forward-filled in the silver layer.
- **IBGE:** population is stored as text with thousands separators (`"22,728"`), and some values carry footnote markers like `(2)`. Cleaned in silver.
- **IBGE year:** the population estimate is for 2020, two years after the Olist data ends. It is used to band cities by size (Small, Medium, Large, Metro), where a two-year gap rarely moves a city between bands.

## Citation

- Olist and André Sionek (2018). *Brazilian E-Commerce Public Dataset by Olist*. Kaggle.
- Federal Reserve Bank of St. Louis. *Brazilian Reals to U.S. Dollar Spot Exchange Rate [DEXBZUS]*. FRED.
- Zippenfenig, P. (2023). *Open-Meteo.com Weather API*. Zenodo.
- World Bank. *World Development Indicators*.
- IBGE. *Estimativas da População Residente nos Municípios Brasileiros, 2020*.
- Nager.Date. *Public Holiday API*.
