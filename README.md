# FlowzzInsight

This repository provides small utilities to explore data from the public Flowzz.com API.

## Components

- `flowzz_product_scraper.py` – downloads product information and ratings.
- `flowzz_viewer.py` – Streamlit application to browse and filter the scraped products.
- `flowzz_pharmacy_finder.py` – Streamlit tool that allows selecting up to three strains and checks which pharmacies offer all of them.

Install the required dependencies with:

```bash
pip install pandas requests streamlit
```

Run the pharmacy finder with:

```bash
streamlit run flowzz_pharmacy_finder.py
```
