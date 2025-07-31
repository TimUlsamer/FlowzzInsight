# Flowzz Insight

This repository contains simple scrapers for the public information available on
[flowzz.com](https://flowzz.com). These tools **do not** perform any purchases or
other regulated actions. They merely download public pages and the Flowzz CMS
API to compile statistics.

## Scripts

- `main.py` – Scrapes general strain statistics (average rating and number of
  likes) and prints a ranked list to the console.
- `product_scraper.py` – Gathers detailed information about individual product
  listings, ranks them by rating, likes and price and saves the data to
  `products.json` and `products.csv`.

## Usage

Run the desired script directly with Python 3:

```bash
python3 product_scraper.py
```

The script will fetch product data from the public CMS and product pages,
compile the statistics, write them to files and display a summary. Network
access to `flowzz.com` is required for real data.
