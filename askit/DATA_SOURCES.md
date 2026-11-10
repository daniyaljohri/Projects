# Data Sources

Askit's code is MIT licensed, like the rest of this repository. The data is not covered by that licence; each source keeps its own terms.

## Olist data

| Item | Detail |
|---|---|
| Dataset | Brazilian E-Commerce Public Dataset by Olist |
| Link | https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce |
| Licence | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |

Askit doesn't load the Olist CSVs itself. It reads the semantic views built on the [Olist Data Warehouse](../olist_data_warehouse), which explains how to download and load the data.

## Enrichment data

The views include exchange rates, macroeconomic indicators, weather and city population from the warehouse's enrichment sources (Open-Meteo, FRED, World Bank, IBGE and Nager.Date). Their links, coverage and licences are listed in the warehouse's [DATA_SOURCES.md](../olist_data_warehouse/DATA_SOURCES.md).

## The SQLite file (`olist.sqlite`)

The SQLite file attached to the GitHub release is a copy of the five `chatbot` views, made with `python -m askit export-sqlite`. It is an adapted version of the Olist dataset combined with the enrichment data above, so:

- it is shared under the same licence as Olist, **CC BY-NC-SA 4.0**: non-commercial use, with attribution, and any adapted version must use the same licence;
- the enrichment sources keep their own attribution requirements, listed in the warehouse's DATA_SOURCES.md;
- it is not covered by the MIT licence of the code.

Attribution: *Olist, Brazilian E-Commerce Public Dataset, Kaggle, licensed under CC BY-NC-SA 4.0. Adapted into semantic views by Daniyal Johri.*
