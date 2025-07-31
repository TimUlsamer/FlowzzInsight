"""Advanced Flowzz Product Scraper
===============================

This script collects product information from Flowzz (https://flowzz.com)
and ranks the available products by various metrics. Compared to the
existing `main.py` script which only scrapes strain data and prints the
results, this program focuses on individual *products* and persists the
collected data for later analysis.

Features
--------
* Retrieves all product entries from the Flowzz CMS REST API.
* Downloads each product detail page to extract likes, rating and price.
* Ranks products by rating, likes and price.
* Saves all data to a CSV file for further processing.

The script only accesses publicly available information and does not
perform any purchasing or account‑related actions.
"""

from __future__ import annotations

import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests

# Configurable constants
REQUEST_DELAY = 0.5  # polite delay between requests
CMS_PRODUCT_URL = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"
OUTPUT_CSV = Path("products.csv")


@dataclass
class ProductData:
    """Container for scraped product information."""

    name: str
    slug: str
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]
    price: Optional[float]

    def product_url(self) -> str:
        return PRODUCT_PAGE_URL.format(slug=self.slug)

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "slug": self.slug,
            "url": self.product_url(),
            "num_likes": self.num_likes,
            "ratings_score": self.ratings_score,
            "ratings_count": self.ratings_count,
            "price": self.price,
        }


def fetch_product_list() -> List[Dict[str, str]]:
    """Return all products from the CMS API."""

    products: List[Dict[str, str]] = []
    page = 1
    page_size = 100

    while True:
        params = {"pagination[page]": page, "pagination[pageSize]": page_size}
        try:
            resp = requests.get(CMS_PRODUCT_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - network
            print(f"[ERROR] Fetching product list page {page}: {exc}", file=sys.stderr)
            break

        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            break

        for entry in entries:
            name = entry.get("name") or entry.get("attributes", {}).get("name") or ""
            slug = entry.get("url") or entry.get("attributes", {}).get("url") or ""
            if name and slug:
                products.append({"name": name, "slug": slug})

        meta = data.get("meta", {}).get("pagination", {})
        if page >= meta.get("pageCount", page):
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return products


def fetch_product_page(slug: str) -> Optional[str]:
    """Return the raw HTML for a product page."""

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
    except Exception as exc:  # pragma: no cover - network
        print(f"[ERROR] Fetching product page '{slug}': {exc}", file=sys.stderr)
        return None


METRIC_PATTERNS = {
    "num_likes": re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE),
    "ratings_score": re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE),
    "ratings_count": re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE),
    "price": re.compile(r'"price"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE),
}


def extract_metrics(html: str) -> Dict[str, Optional[float]]:
    """Extract likes, rating and price from a product page."""

    metrics: Dict[str, Optional[float]] = {key: None for key in METRIC_PATTERNS}
    for key, pattern in METRIC_PATTERNS.items():
        match = pattern.search(html)
        if match:
            value: Optional[float] = None
            if key in ("num_likes", "ratings_count"):
                value = int(match.group(1))
            else:
                value = float(match.group(1))
            metrics[key] = value
    return metrics


def scrape_products() -> List[ProductData]:
    """Collect information for every product listed on Flowzz."""

    product_refs = fetch_product_list()
    results: List[ProductData] = []
    total = len(product_refs)

    for idx, ref in enumerate(product_refs, start=1):
        name = ref["name"]
        slug = ref["slug"]
        print(f"[{idx}/{total}] {name}")

        html = fetch_product_page(slug)
        if not html:
            results.append(
                ProductData(
                    name=name,
                    slug=slug,
                    num_likes=None,
                    ratings_score=None,
                    ratings_count=None,
                    price=None,
                )
            )
            continue

        metrics = extract_metrics(html)
        results.append(
            ProductData(
                name=name,
                slug=slug,
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
                price=metrics.get("price"),
            )
        )
        time.sleep(REQUEST_DELAY)

    return results


def save_to_csv(products: List[ProductData], csv_path: Path) -> None:
    """Save all product data to ``csv_path``."""

    fieldnames = [
        "name",
        "slug",
        "url",
        "num_likes",
        "ratings_score",
        "ratings_count",
        "price",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for prod in products:
            writer.writerow(prod.as_dict())


def print_rankings(products: List[ProductData]) -> None:
    """Display ranking tables for the scraped products."""

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
        key=lambda p: (-(p.num_likes if p.num_likes is not None else -1), p.name.lower()),
    )

    price_known = [p for p in products if p.price is not None]
    by_price = sorted(price_known, key=lambda p: p.price)

    def table(title: str, rows: List[ProductData], metric: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<40} | {metric:>12} | {'Link'}"
        print(header)
        print("-" * len(header))
        for i, prod in enumerate(rows, 1):
            value = getattr(prod, metric)
            metric_val = f"{value}" if value is not None else "N/A"
            print(f"{i:>4} | {prod.name:<40} | {metric_val:>12} | {prod.product_url()}")

    table("Products by Rating", by_rating, "ratings_score")
    table("Products by Likes", by_likes, "num_likes")
    if by_price:
        table("Products by Price (asc)", by_price, "price")


def main() -> None:
    products = scrape_products()
    save_to_csv(products, OUTPUT_CSV)
    print_rankings(products)
    print(f"\nData saved to {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()
