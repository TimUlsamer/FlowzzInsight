"""
Flowzz Strain Scraper
----------------------

This script queries the public CMS and website of the price comparison
platform `flowzz.com` to retrieve a list of all currently available
cannabis flower strains (“Blüten”) and extract two key metrics for each
strain:

* **Star rating** – the average score (out of 5) that users have
  assigned to the strain.
* **Number of likes** – how many users have liked the strain.  This
  figure is visible on the individual strain’s detail page.

The script performs the following high‑level steps:

1. **Retrieve all strain slugs via the CMS API.**  The Flowzz CMS
   exposes a REST endpoint (`/api/strains`) which returns basic
   information about every strain, including a URL slug.  By paging
   through this endpoint we obtain a complete list of strains and their
   human‑readable names.
2. **Scrape each strain’s detail page.**  For every slug, the script
   downloads the corresponding page (`https://flowzz.com/strain/<slug>`)
   and looks for a JSON object embedded in the page markup.  This
   object contains, among other things, the total number of likes
   (`num_likes`), the average rating (`ratings_score`) and the number
   of ratings (`ratings_count`).  We extract these values with regular
   expressions.
3. **Aggregate and sort.**  After collecting metrics for every strain,
   the script prints two lists to standard output:
   * strains sorted by descending star rating, and
   * strains sorted by descending number of likes.

Usage
-----

Run the script directly with Python 3:

```
python flowzz_scraper.py
```

The script will report progress to the console and may take several
minutes to complete depending on the number of strains and network
latency.  To be polite to Flowzz’s servers, a small delay is inserted
between requests.  You can adjust the delay via the `REQUEST_DELAY`
constant.

Note
----

This script accesses publicly available information on flowzz.com.  It
does **not** perform any purchases or other regulated transactions.  If
Flowzz changes its page structure or API, the regular expressions may
require adjustment.
"""

import argparse
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional

from tabulate import tabulate
from tqdm import tqdm

import requests

# A polite delay between HTTP requests (in seconds). Can be overridden via CLI.
REQUEST_DELAY = 0.5

# Base URLs used by the scraper.
CMS_BASE_URL = "https://cms.flowzz.com/api/strains"
STRAIN_PAGE_URL = "https://flowzz.com/strain/{slug}"


@dataclass
class StrainData:
    """Container for extracted strain statistics."""

    name: str
    slug: str
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]

    @property
    def url(self) -> str:
        """Return the full Flowzz URL for this strain."""
        return STRAIN_PAGE_URL.format(slug=self.slug)

    def as_dict(self) -> Dict[str, Optional[str]]:
        """Return a dict representation of the strain for easy sorting."""
        return {
            "name": self.name,
            "slug": self.slug,
            "num_likes": self.num_likes,
            "ratings_score": self.ratings_score,
            "ratings_count": self.ratings_count,
        }


def fetch_strain_list() -> List[Dict[str, str]]:
    """Fetch all strains from the CMS API.

    Returns a list of dictionaries with at least `name` and `slug` keys.
    The CMS API paginates results; this function iterates through all
    pages until no more data is returned.
    """
    strains: List[Dict[str, str]] = []
    page = 1
    page_size = 100  # Reasonable page size to limit request count

    while True:
        params = {
            "pagination[page]": page,
            "pagination[pageSize]": page_size,
        }
        try:
            resp = requests.get(CMS_BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[ERROR] Failed to fetch strain list on page {page}: {exc}", file=sys.stderr)
            break

        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            break

        for entry in entries:
            # The CMS returns entries either as objects or nested under
            # 'attributes'; older entries may not include 'attributes'.
            if isinstance(entry, dict):
                # Modern CMS entries are objects with top‑level keys.
                name = entry.get("name") or entry.get("attributes", {}).get("name") or ""
                slug = entry.get("url") or entry.get("attributes", {}).get("url") or ""
                if name and slug:
                    strains.append({"name": name, "slug": slug})

        # Pagination metadata is available under meta.pagination.  Stop when
        # we reach the last page.
        meta = data.get("meta", {})
        pagination = meta.get("pagination", {})
        total_pages = pagination.get("pageCount")
        if total_pages is None or page >= total_pages:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    return strains


def extract_metrics_from_html(html: str) -> Dict[str, Optional[float]]:
    """Extract the numeric metrics from a strain detail page.

    The Flowzz strain pages embed a JSON object containing various
    attributes, including `num_likes`, `ratings_score` and
    `ratings_count`.  This function uses regular expressions to locate
    those values.  If a metric cannot be found, its value in the
    returned dictionary will be `None`.
    """
    # Patterns to capture numbers.  We allow optional whitespace to
    # accommodate minified or formatted JSON.
    like_pattern = re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE)
    score_pattern = re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    count_pattern = re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE)

    metrics: Dict[str, Optional[float]] = {
        "num_likes": None,
        "ratings_score": None,
        "ratings_count": None,
    }

    like_match = like_pattern.search(html)
    if like_match:
        metrics["num_likes"] = int(like_match.group(1))

    score_match = score_pattern.search(html)
    if score_match:
        metrics["ratings_score"] = float(score_match.group(1))

    count_match = count_pattern.search(html)
    if count_match:
        metrics["ratings_count"] = int(count_match.group(1))

    return metrics


def save_to_csv(strains: List[StrainData], path: str) -> None:
    """Write the scraped data to a CSV file."""
    fieldnames = [
        "name",
        "slug",
        "url",
        "num_likes",
        "ratings_score",
        "ratings_count",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in strains:
            writer.writerow(
                {
                    "name": s.name,
                    "slug": s.slug,
                    "url": s.url,
                    "num_likes": s.num_likes,
                    "ratings_score": s.ratings_score,
                    "ratings_count": s.ratings_count,
                }
            )


def save_to_json(strains: List[StrainData], path: str) -> None:
    """Write the scraped data to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump([s.as_dict() | {"url": s.url} for s in strains], f, indent=2)


def fetch_strain_page(slug: str) -> Optional[str]:
    """Download the HTML for a strain detail page.

    The function returns the raw HTML text or None if an error occurs.
    A custom User‑Agent header is used to resemble a normal browser.
    """
    url = STRAIN_PAGE_URL.format(slug=slug)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0 Safari/537.36"
        ),
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"[ERROR] Failed to fetch strain page '{slug}': {exc}", file=sys.stderr)
        return None

    finally:
        # Always be polite and pause between requests
        time.sleep(REQUEST_DELAY)
    

def scrape_flowzz(concurrency: int = 5) -> List[StrainData]:
    """Collect statistics for all strains using concurrent requests."""

    strains_info = fetch_strain_list()
    results: List[StrainData] = []

    def process(entry: Dict[str, str]) -> StrainData:
        name = entry["name"]
        slug = entry["slug"]
        html = fetch_strain_page(slug)
        if not html:
            metrics = {"num_likes": None, "ratings_score": None, "ratings_count": None}
        else:
            metrics = extract_metrics_from_html(html)
        return StrainData(
            name=name,
            slug=slug,
            num_likes=metrics.get("num_likes"),
            ratings_score=metrics.get("ratings_score"),
            ratings_count=metrics.get("ratings_count"),
        )

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(process, entry) for entry in strains_info]
        for future in tqdm(as_completed(futures), total=len(futures), desc="Scraping"):
            results.append(future.result())

    return results


def print_sorted_lists(strains: List[StrainData], limit: int = 20) -> None:
    """Print tables of strains sorted by rating and likes."""

    by_rating = sorted(
        strains,
        key=lambda s: (
            -(s.ratings_score if s.ratings_score is not None else -1.0),
            -(s.ratings_count if s.ratings_count is not None else 0),
            s.name.lower(),
        ),
    )

    by_likes = sorted(
        strains,
        key=lambda s: (
            -(s.num_likes if s.num_likes is not None else -1),
            s.name.lower(),
        ),
    )

    def to_table(entries: List[StrainData], metric_key: str) -> str:
        rows = []
        for rank, s in enumerate(entries[:limit], start=1):
            metric_val = getattr(s, metric_key)
            rows.append([
                rank,
                s.name,
                s.url,
                metric_val if metric_val is not None else "N/A",
            ])
        return tabulate(
            rows,
            headers=["Rank", "Strain", "URL", metric_key.replace("_", " ").title()],
            tablefmt="github",
        )

    print("\nStrains nach Sternebewertung (absteigend)")
    print(to_table(by_rating, "ratings_score"))
    print("\nStrains nach Likes (absteigend)")
    print(to_table(by_likes, "num_likes"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape strain statistics from flowzz.com")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of parallel requests")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Delay between requests in seconds")
    parser.add_argument("--csv", metavar="PATH", help="Write results to CSV file")
    parser.add_argument("--json", metavar="PATH", help="Write results to JSON file")
    parser.add_argument("--limit", type=int, default=20, help="Number of rows to display")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global REQUEST_DELAY
    REQUEST_DELAY = args.delay

    strains = scrape_flowzz(concurrency=args.concurrency)
    print_sorted_lists(strains, limit=args.limit)

    if args.csv:
        save_to_csv(strains, args.csv)
    if args.json:
        save_to_json(strains, args.json)


if __name__ == "__main__":
    main()
