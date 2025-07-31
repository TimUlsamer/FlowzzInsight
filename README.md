# FlowzzInsight

This utility scrapes strain statistics from [flowzz.com](https://flowzz.com).
It queries the public CMS for available strains and then fetches each strain's
page to extract the number of likes and the average user rating.

## Features

- Concurrent scraping for faster execution
- Command line interface with options for concurrency and request delay
- Results saved to CSV and/or JSON if desired
- Nicely formatted tables with direct links to each strain

## Usage

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Run the scraper:

```bash
python main.py --csv strains.csv --json strains.json --limit 30
```

This will print the top strains by rating and likes, while also writing all
scraped data to `strains.csv` and `strains.json`.
