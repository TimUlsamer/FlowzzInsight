# FlowzzInsight

Scripts for scraping publicly visible information from [Flowzz.com](https://flowzz.com).

## `main.py`
Retrieves statistics for all strains listed on Flowzz and prints basic
rankings by rating and number of likes.

## `product_scraper.py`
An extended scraper that collects information about every individual
product.  It stores the results in `products.json` and `products.csv` and
also prints rankings to the console.

### Usage

```bash
python product_scraper.py
```

The script will access Flowzz's public CMS API and product pages.  Results
are written to `products.json` and `products.csv` in the repository
folder.
