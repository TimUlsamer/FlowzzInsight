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

import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

# A polite delay between HTTP requests (in seconds).
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


def print_sorted_lists(strains: List[StrainData]) -> None:
    """Print strains sorted by rating and by likes.

    Strains with missing values are placed at the end of each list.  The
    function prints a simple table for each sorting criterion.
    """
    # Sort by rating score (descending).  Use -score for proper ordering,
    # None values are treated as -1 so they sink to the bottom.
    by_rating = sorted(
        strains,
        key=lambda s: (
            -(s.ratings_score if s.ratings_score is not None else -1.0),
            -(s.ratings_count if s.ratings_count is not None else 0),
            s.name.lower(),
        ),
    )

    # Sort by number of likes (descending).  None values are treated as -1.
    by_likes = sorted(
        strains,
        key=lambda s: (
            -(s.num_likes if s.num_likes is not None else -1),
            s.name.lower(),
        ),
    )

    def print_table(title: str, entries: List[StrainData], metric_key: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Strain':<40} | {metric_key.replace('_', ' ').title():>12}"
        print(header)
        print("-" * len(header))
        for rank, strain in enumerate(entries, start=1):
            metric_value = getattr(strain, metric_key)
            metric_str = f"{metric_value}" if metric_value is not None else "N/A"
            print(f"{rank:>4} | {strain.name:<40} | {metric_str:>12}")

    print_table("Strains nach Sternebewertung (absteigend)", by_rating, "ratings_score")
    print_table("Strains nach Likes (absteigend)", by_likes, "num_likes")


def main() -> None:
    strains = scrape_flowzz()
    print_sorted_lists(strains)


if __name__ == "__main__":
    main()