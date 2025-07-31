"""Flowzz strain scraper.

This tool queries the public CMS and website of ``flowzz.com`` to gather
statistics for every listed flower strain. Compared to the earlier
version it offers a small command line interface, CSV/JSON export and
prettier console tables.

The program **does not** perform any purchases or other regulated
transactions. It merely accesses information already visible on the
website. Should Flowzz change its page structure, the regular
expressions below may require adjustment.
"""

import argparse
import csv
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
from tabulate import tabulate

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

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
            logging.error("Failed to fetch strain list on page %s: %s", page, exc)
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
        logging.error("Failed to fetch strain page '%s': %s", slug, exc)
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
        logging.info("Processing %s/%s: %s (%s)", idx, total, name, slug)
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


def save_to_csv(strains: List[StrainData], path: Path) -> None:
    """Write the scraped data to a CSV file."""
    fieldnames = [
        "name",
        "slug",
        "url",
        "ratings_score",
        "ratings_count",
        "num_likes",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in strains:
            writer.writerow(
                {
                    "name": s.name,
                    "slug": s.slug,
                    "url": STRAIN_PAGE_URL.format(slug=s.slug),
                    "ratings_score": s.ratings_score,
                    "ratings_count": s.ratings_count,
                    "num_likes": s.num_likes,
                }
            )


def save_to_json(strains: List[StrainData], path: Path) -> None:
    """Write the scraped data to a JSON file."""
    data = [
        {
            **s.as_dict(),
            "url": STRAIN_PAGE_URL.format(slug=s.slug),
        }
        for s in strains
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def print_sorted_lists(strains: List[StrainData], limit: int = 10) -> None:
    """Print strains sorted by rating and by likes.

    Parameters
    ----------
    strains:
        Collection of :class:`StrainData` objects.
    limit:
        Only print the top ``limit`` entries of each table.
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
        table = []
        for rank, strain in enumerate(entries[:limit], start=1):
            metric_value = getattr(strain, metric_key)
            table.append(
                [
                    rank,
                    strain.name,
                    STRAIN_PAGE_URL.format(slug=strain.slug),
                    metric_value if metric_value is not None else "N/A",
                ]
            )
        print("\n" + title)
        print(tabulate(table, headers=["#", "Strain", "URL", metric_key.replace("_", " ").title()], tablefmt="github"))

    print_table("Strains nach Sternebewertung (absteigend)", by_rating, "ratings_score")
    print_table("Strains nach Likes (absteigend)", by_likes, "num_likes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape strain data from flowzz.com")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write results to the given CSV file (also writes JSON with same name).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of entries to show in the summary tables.",
    )
    args = parser.parse_args()

    strains = scrape_flowzz()
    print_sorted_lists(strains, limit=args.limit)

    if args.output:
        save_to_csv(strains, args.output)
        save_to_json(strains, args.output.with_suffix(".json"))


if __name__ == "__main__":
    main()