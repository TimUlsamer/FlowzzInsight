"""Flowzz Product Scraper
=======================

This utility enumerates all cannabis products listed on `flowzz.com` and
collects key information from their detail pages.  Compared to the basic
strain scraper, this script focuses on the full product pages (e.g.
`https://flowzz.com/product/<slug>`) rather than the generic strain
pages.

The script performs these steps:

1. Retrieve all product slugs from Flowzz's public CMS API.
2. Download each product page and extract statistics such as the star
   rating, number of ratings and likes.
3. Store the data in a CSV file and present summary rankings directly on
   the console.

Because Flowzz may adjust its public API at any time, some fields could
be missing from the CMS responses.  Missing values are recorded as
`None` in the output file.

Note: Running this tool sends a series of HTTP GET requests to
`flowzz.com`.  Please respect their terms of service and avoid excessive
traffic.  A small delay between requests is enforced by default.
"""

from __future__ import annotations

import csv
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import requests

# Delay between HTTP requests so we do not overwhelm the server.
REQUEST_DELAY = 0.5

# Endpoints for the CMS API and product pages.
CMS_PRODUCTS_URL = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"


@dataclass
class ProductData:
    """Structured information about a single Flowzz product."""

    name: str
    slug: str
    strain_name: Optional[str]
    price: Optional[float]
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]

    @property
    def url(self) -> str:
        """Return the full product URL."""
        return PRODUCT_PAGE_URL.format(slug=self.slug)


def paginate_cms(endpoint: str) -> Iterable[Dict[str, object]]:
    """Iterate through all pages of a CMS endpoint."""

    page = 1
    page_size = 100

    while True:
        params = {
            "pagination[page]": page,
            "pagination[pageSize]": page_size,
        }
        try:
            resp = requests.get(endpoint, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[ERROR] CMS request failed on page {page}: {exc}", file=sys.stderr)
            break

        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            break

        for entry in entries:
            if isinstance(entry, dict):
                yield entry

        meta = data.get("meta", {})
        pagination = meta.get("pagination", {})
        total_pages = pagination.get("pageCount")
        if total_pages is None or page >= total_pages:
            break
        page += 1
        time.sleep(REQUEST_DELAY)


def fetch_product_list() -> List[Dict[str, object]]:
    """Return a list of product info dictionaries from the CMS."""

    products: List[Dict[str, object]] = []
    for entry in paginate_cms(CMS_PRODUCTS_URL):
        name = entry.get("name") or entry.get("attributes", {}).get("name")
        slug = entry.get("url") or entry.get("attributes", {}).get("url")
        strain = entry.get("strain") or entry.get("attributes", {}).get("strain")
        price_raw = (
            entry.get("price")
            or entry.get("attributes", {}).get("price")
            or entry.get("price_per_unit")
            or entry.get("attributes", {}).get("price_per_unit")
        )
        price = None
        if isinstance(price_raw, (int, float, str)):
            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                price = None

        if name and slug:
            products.append({
                "name": name,
                "slug": slug,
                "strain_name": strain,
                "price": price,
            })
    return products


METRIC_PATTERNS = {
    "num_likes": re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE),
    "ratings_score": re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE),
    "ratings_count": re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE),
}


def fetch_product_page(slug: str) -> Optional[str]:
    """Download a product page HTML document."""

    url = PRODUCT_PAGE_URL.format(slug=slug)
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
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"[ERROR] Failed to fetch product page '{slug}': {exc}", file=sys.stderr)
        return None


def extract_metrics(html: str) -> Dict[str, Optional[float]]:
    """Extract ratings metrics from the HTML markup."""

    metrics: Dict[str, Optional[float]] = {
        "num_likes": None,
        "ratings_score": None,
        "ratings_count": None,
    }

    for key, pattern in METRIC_PATTERNS.items():
        match = pattern.search(html)
        if match:
            value = match.group(1)
            metrics[key] = float(value) if "." in value else int(value)

    return metrics


def scrape_products() -> List[ProductData]:
    """Gather statistics for all products."""

    products_info = fetch_product_list()
    results: List[ProductData] = []
    total = len(products_info)
    for idx, info in enumerate(products_info, start=1):
        name = str(info.get("name"))
        slug = str(info.get("slug"))
        print(f"Processing {idx}/{total}: {name} ({slug})")
        html = fetch_product_page(slug)
        metrics = extract_metrics(html or "") if html else {
            "num_likes": None,
            "ratings_score": None,
            "ratings_count": None,
        }
        results.append(
            ProductData(
                name=name,
                slug=slug,
                strain_name=info.get("strain_name"),
                price=info.get("price"),
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
            )
        )
        time.sleep(REQUEST_DELAY)
    return results


def save_to_csv(products: List[ProductData], filename: str) -> None:
    """Save product data to a CSV file."""

    fieldnames = [
        "name",
        "slug",
        "url",
        "strain_name",
        "price",
        "ratings_score",
        "ratings_count",
        "num_likes",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in products:
            writer.writerow({
                "name": p.name,
                "slug": p.slug,
                "url": p.url,
                "strain_name": p.strain_name or "",
                "price": p.price if p.price is not None else "",
                "ratings_score": p.ratings_score if p.ratings_score is not None else "",
                "ratings_count": p.ratings_count if p.ratings_count is not None else "",
                "num_likes": p.num_likes if p.num_likes is not None else "",
            })


def rank_and_print(products: List[ProductData]) -> None:
    """Display ranking tables sorted by rating and likes."""

    by_rating = sorted(
        products,
        key=lambda p: (
            -(p.ratings_score if p.ratings_score is not None else -1.0),
            -(p.ratings_count if p.ratings_count is not None else 0),
            p.name.lower(),
        ),
    )
    by_likes = sorted(
        products,
        key=lambda p: (
            -(p.num_likes if p.num_likes is not None else -1),
            p.name.lower(),
        ),
    )

    def table(title: str, items: List[ProductData], metric: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<40} | {metric.replace('_', ' ').title():>12} | URL"
        print(header)
        print("-" * len(header))
        for rank, prod in enumerate(items, start=1):
            value = getattr(prod, metric)
            value_str = f"{value}" if value is not None else "N/A"
            print(f"{rank:>4} | {prod.name:<40} | {value_str:>12} | {prod.url}")

    table("Products by Rating", by_rating, "ratings_score")
    table("Products by Likes", by_likes, "num_likes")


def main() -> None:
    products = scrape_products()
    save_to_csv(products, "products.csv")
    rank_and_print(products)


if __name__ == "__main__":
    main()
