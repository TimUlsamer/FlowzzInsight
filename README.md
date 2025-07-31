# FlowzzInsight

This tool scrapes publicly available statistics about cannabis flower strains from [flowzz.com](https://flowzz.com).
It collects each strain's likes and user rating and stores the data in a CSV or JSON file.

## Usage

Run the scraper with Python 3:

```bash
python main.py [-o OUTPUT] [--json] [--no-tables]
```

- `-o`, `--output`  Path to the file where results are written (default: `strain_data.csv`).
- `--json`          Save the results in JSON format instead of CSV.
- `--no-tables`     Suppress printing summary tables to the console.

Example:

```bash
python main.py -o strains.json --json
```

The script iterates through all strains exposed by the Flowzz CMS, retrieves
statistics from each strain page, and writes the aggregated data to the chosen
output file.  A small delay between requests keeps the load on Flowzz's servers
low.

