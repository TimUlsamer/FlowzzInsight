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
   the script writes the data to a file (CSV or JSON) and prints two
   ranked tables:
   * strains sorted by descending star rating, and
   * strains sorted by descending number of likes.

Usage
-----

Run the script directly with Python 3.  Use ``--help`` to see all
available options:

```
python flowzz_scraper.py --help
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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests

# Default delay between HTTP requests (in seconds). Can be overridden via CLI.
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


def scrape_flowzz() -> List[StrainData]:
    """Collect statistics for all strains.

    Returns a list of StrainData objects.
    """
    strains_info = fetch_strain_list()
    results: List[StrainData] = []
    total = len(strains_info)
    for idx, entry in enumerate(strains_info, start=1):
        name = entry["name"]
        slug = entry["slug"]
        print(f"Processing {idx}/{total}: {name} ({slug})")
        html = fetch_strain_page(slug)
        if not html:
            # Skip if we couldn't download the page.
            results.append(
                StrainData(name=name, slug=slug, num_likes=None, ratings_score=None, ratings_count=None)
            )
            continue
        metrics = extract_metrics_from_html(html)
        results.append(
            StrainData(
                name=name,
                slug=slug,
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
            )
        )
        time.sleep(REQUEST_DELAY)
    return results


def save_results(strains: List[StrainData], path: Path, fmt: str = "csv") -> None:
    """Save the scraped data to ``path``.

    Parameters
    ----------
    strains:
        List of :class:`StrainData` objects to persist.
    path:
        Destination file path.
    fmt:
        Either ``"csv"`` or ``"json"``.
    """
    path = Path(path)
    if fmt.lower() == "json":
        with path.open("w", encoding="utf-8") as fh:
            json.dump([s.as_dict() for s in strains], fh, ensure_ascii=False, indent=2)
    else:
        with path.open("w", newline="", encoding="utf-8") as fh:
            fieldnames = [
                "name",
                "slug",
                "url",
                "ratings_score",
                "ratings_count",
                "num_likes",
            ]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for s in strains:
                row = s.as_dict()
                row["url"] = STRAIN_PAGE_URL.format(slug=s.slug)
                writer.writerow(row)
    print(f"Saved results to {path.resolve()}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Scrape strain statistics from flowzz.com")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("flowzz_strains.csv"),
        help="File to save the results (default: flowzz_strains.csv)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Output file format",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help="Delay between HTTP requests in seconds",
    )
    parser.add_argument(
        "-t",
        "--top",
        type=int,
        default=20,
        help="Number of entries to display in the ranking tables",
    )
    return parser.parse_args()


def print_sorted_lists(strains: List[StrainData], *, top_n: int = 20) -> None:
    """Print ranking tables for the scraped strains.

    Parameters
    ----------
    strains:
        The collected strain data.
    top_n:
        Limit output to the top ``n`` entries for each ranking.
    """

    def sort_by_rating(item: StrainData) -> tuple:
        return (
            -(item.ratings_score if item.ratings_score is not None else -1.0),
            -(item.ratings_count if item.ratings_count is not None else 0),
            item.name.lower(),
        )

    def sort_by_likes(item: StrainData) -> tuple:
        return (
            -(item.num_likes if item.num_likes is not None else -1),
            item.name.lower(),
        )

    by_rating = sorted(strains, key=sort_by_rating)
    by_likes = sorted(strains, key=sort_by_likes)

    def print_table(title: str, entries: List[StrainData]) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = (
            f"{'Rank':>4}  {'Strain':<30}  {'Rating':>6}  "
            f"{'Votes':>5}  {'Likes':>5}  {'URL'}"
        )
        print(header)
        print("-" * len(header))
        for rank, strain in enumerate(entries[:top_n], start=1):
            url = STRAIN_PAGE_URL.format(slug=strain.slug)
            rating = (
                f"{strain.ratings_score:.2f}" if strain.ratings_score is not None else "N/A"
            )
            votes = (
                f"{strain.ratings_count}" if strain.ratings_count is not None else "N/A"
            )
            likes = f"{strain.num_likes}" if strain.num_likes is not None else "N/A"
            print(
                f"{rank:>4}  {strain.name:<30}  {rating:>6}  {votes:>5}  {likes:>5}  {url}"
            )

    print_table("Top Strains by Rating", by_rating)
    print_table("Top Strains by Likes", by_likes)


def main() -> None:
    args = parse_args()
    global REQUEST_DELAY
    REQUEST_DELAY = args.delay

    strains = scrape_flowzz()
    print_sorted_lists(strains, top_n=args.top)
    save_results(strains, args.output, args.format)


if __name__ == "__main__":
    main()