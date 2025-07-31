# FlowzzInsight

This utility gathers public statistics for cannabis flower strains listed on
[flowzz.com](https://flowzz.com).  It queries the Flowzz CMS for available
strains and scrapes each detail page to collect the number of likes and the
average star rating.  The results are written to a CSV or JSON file and a
compact ranking is printed to the console.

## Usage

```bash
python flowzz_scraper.py --help
```

The command‐line interface lets you control the output location and format, the
request delay and how many entries to display in the ranking tables.

Example:

```bash
python flowzz_scraper.py -o results.csv -f csv --delay 1.0 --top 10
```

This will save a ``results.csv`` file and show the top 10 strains sorted by
rating and by number of likes.

