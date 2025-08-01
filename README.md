# FlowzzInsight

Utilities for scraping product data from Flowzz and exploring it.

## Scripts

- `flowzz_product_scraper.py` – fetches product listing and like counts.
- `flowzz_viewer.py` – Streamlit app to interactively explore scraped data.
- `flowzz_vendor_search.py` – helper to list vendors stocking a set of products.

## Vendor Search Usage

```
python flowzz_vendor_search.py <slug1> [<slug2> <slug3>]
```

Provide up to three product slugs from Flowzz. The script queries the detail API
for each product, extracts vendor/shop information and prints the vendors that
carry all the given products.

Note: API access to flowzz.com may require an internet connection.
