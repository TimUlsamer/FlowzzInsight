# FlowzzInsight

Utilities for interacting with the public API of [flowzz.com](https://flowzz.com). The project contains a scraper for product data and a simple viewer built with Streamlit.

## Requirements

- Python 3.11+
- `requests`
- `pandas`
- `streamlit` (for the viewer)

Install dependencies via pip:

```bash
pip install requests pandas streamlit
```

## Product Scraper

`flowzz_product_scraper.py` downloads metadata about all cannabis flower products and writes CSV files sorted by likes and rating.

Run the scraper:

```bash
python flowzz_product_scraper.py
```

## Pharmacy Finder

`flowzz_pharmacy_finder.py` helps to locate pharmacies that stock selected strains. It mimics the pharmacy search behaviour of the [Flowzz Shopping Helper](https://github.com/FrittenToni/flowzz-shopping-helper).

When executed it downloads the list of strains, lets you enter up to three strain names and then queries the pharmacy API to find vendors that offer **all** of them.

```bash
python flowzz_pharmacy_finder.py
```

The script prints a table with vendor names and prices. Note that network access to `flowzz.com` is required for it to work.

