"""Flowzz Product Scraper
-----------------------

This script retrieves information about individual cannabis products
listed on ``flowzz.com``. It queries the public CMS API to obtain a
list of product slugs and then visits each corresponding product page to
extract useful metrics such as price, rating score and number of likes.

The gathered data are written to a CSV file and the products are also
ranked according to different criteria (rating score and price). The
results are printed in a compact table for quick inspection.

The script mirrors the behaviour of :mod:`main` (strain scraper) but
operates on the ``/product`` pages instead of ``/strain``.
"""

from __future__ import annotations

import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

# Delay between HTTP requests to avoid overloading the server.
REQUEST_DELAY = 0.5

CMS_BASE_URL = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"
OUTPUT_FILE = Path("products.csv")


@dataclass
class ProductData:
    """Container for extracted product statistics."""

    name: str
    slug: str
    price: Optional[float]
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]

    @property
    def url(self) -> str:
        return PRODUCT_PAGE_URL.format(slug=self.slug)

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "slug": self.slug,
            "url": self.url,
            "price": self.price,
            "num_likes": self.num_likes,
            "ratings_score": self.ratings_score,
            "ratings_count": self.ratings_count,
        }


def fetch_product_list() -> List[Dict[str, str]]:
    """Retrieve all product entries from the CMS API."""

    products: List[Dict[str, str]] = []
    page = 1
    page_size = 100

    while True:
        params = {"pagination[page]": page, "pagination[pageSize]": page_size}
        try:
            resp = requests.get(CMS_BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - network errors
            print(f"[ERROR] Failed to fetch product list on page {page}: {exc}", file=sys.stderr)
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
        if page >= meta.get("pageCount", 0):
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    return products


PRICE_PATTERN = re.compile(r'"price"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
LIKE_PATTERN = re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE)
SCORE_PATTERN = re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
COUNT_PATTERN = re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE)


def extract_metrics_from_html(html: str) -> Dict[str, Optional[float]]:
    """Extract relevant metrics from a product page."""

    metrics: Dict[str, Optional[float]] = {
        "price": None,
        "num_likes": None,
        "ratings_score": None,
        "ratings_count": None,
    }

    match = PRICE_PATTERN.search(html)
    if match:
        metrics["price"] = float(match.group(1))

    match = LIKE_PATTERN.search(html)
    if match:
        metrics["num_likes"] = int(match.group(1))

    match = SCORE_PATTERN.search(html)
    if match:
        metrics["ratings_score"] = float(match.group(1))

    match = COUNT_PATTERN.search(html)
    if match:
        metrics["ratings_count"] = int(match.group(1))

    return metrics


def fetch_product_page(slug: str) -> Optional[str]:
    """Download the HTML for a product detail page."""

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
    except Exception as exc:  # pragma: no cover - network errors
        print(f"[ERROR] Failed to fetch product page '{slug}': {exc}", file=sys.stderr)
        return None


def scrape_products() -> List[ProductData]:
    """Collect statistics for all products."""

    product_info = fetch_product_list()
    results: List[ProductData] = []
    total = len(product_info)
    for idx, entry in enumerate(product_info, start=1):
        name = entry["name"]
        slug = entry["slug"]
        print(f"Processing {idx}/{total}: {name} ({slug})")
        html = fetch_product_page(slug)
        if not html:
            results.append(
                ProductData(name=name, slug=slug, price=None, num_likes=None, ratings_score=None, ratings_count=None)
            )
            continue
        metrics = extract_metrics_from_html(html)
        results.append(
            ProductData(
                name=name,
                slug=slug,
                price=metrics.get("price"),
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
            )
        )
        time.sleep(REQUEST_DELAY)

    return results


def save_to_csv(products: Iterable[ProductData], path: Path = OUTPUT_FILE) -> None:
    """Save the collected product data to a CSV file."""

    fieldnames = ["name", "slug", "url", "price", "num_likes", "ratings_score", "ratings_count"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for prod in products:
            writer.writerow(prod.as_dict())


def print_sorted_tables(products: List[ProductData]) -> None:
    """Print products sorted by rating and by price."""

    by_rating = sorted(
        products,
        key=lambda p: (
            -(p.ratings_score if p.ratings_score is not None else -1.0),
            -(p.ratings_count if p.ratings_count is not None else 0),
            p.name.lower(),
        ),
    )

    by_price = sorted(
        products,
        key=lambda p: (
            p.price if p.price is not None else float("inf"),
            p.name.lower(),
        ),
    )

    def print_table(title: str, entries: List[ProductData], metric_key: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<40} | {metric_key.replace('_', ' ').title():>12} | {'Link'}"
        print(header)
        print("-" * len(header))
        for rank, prod in enumerate(entries, start=1):
            metric_value = getattr(prod, metric_key)
            metric_str = f"{metric_value}" if metric_value is not None else "N/A"
            print(f"{rank:>4} | {prod.name:<40} | {metric_str:>12} | {prod.url}")

    print_table("Produkte nach Bewertung (absteigend)", by_rating, "ratings_score")
    print_table("Produkte nach Preis (aufsteigend)", by_price, "price")


def main() -> None:
    products = scrape_products()
    save_to_csv(products)
    print_sorted_tables(products)


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
