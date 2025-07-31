Flowzz Insight
==============

This repository contains two Python scripts for gathering publicly
visible statistics from `flowzz.com`:

* **main.py** – Scrapes general strain pages and prints simple
  rankings for strains based on star rating and number of likes.
* **product_scraper.py** – NEW.  Collects data for each individual
  product (e.g. `https://flowzz.com/product/...`) and stores the
  results in `products.json` and `products.csv`.  The script also
  prints ranking tables by rating and by price.

Both scripts require outbound network access to `flowzz.com`.  Run them
with Python 3.  For example:

```bash
python product_scraper.py
```

The scripts do not perform any purchases or other regulated
transactions; they merely read data that is publicly available.

