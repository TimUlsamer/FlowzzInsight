"""Flowzz Product Scraper
-----------------------

This script collects statistics for all flower products on flowzz.com.
Unlike the strain scraper in ``main.py`` which looks at generic strain
pages, this program targets individual product listings under
``https://flowzz.com/product/<slug>``.  For each product we attempt to
collect metrics that are publicly visible, such as price, rating and
number of likes.

The data is stored in both CSV and JSON formats for later analysis.  In
addition, the script prints simple ranking tables based on rating and
price.

Network access to ``flowzz.com`` is required for the script to function.
If the website structure changes the regular expressions may need
adjustment.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

import requests

# Polite delay between HTTP requests
REQUEST_DELAY = 0.5

# Base URLs used by the scraper
CMS_BASE_URL = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"
OUTPUT_JSON = Path("products.json")
OUTPUT_CSV = Path("products.csv")


@dataclass
class ProductData:
    """Container for extracted product information."""

    name: str
    slug: str
    url: str
    price: Optional[float]
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]

    def as_dict(self) -> Dict[str, Optional[str]]:
        data = asdict(self)
        # Convert Path object to string if present
        data["url"] = self.url
        return data


def fetch_product_list() -> List[Dict[str, str]]:
    """Retrieve all products from the CMS API."""
    products: List[Dict[str, str]] = []
    page = 1
    page_size = 100

    while True:
        params = {
            "pagination[page]": page,
            "pagination[pageSize]": page_size,
        }
        try:
            resp = requests.get(CMS_BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[ERROR] Failed to fetch product list page {page}: {exc}", file=sys.stderr)
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

        meta = data.get("meta", {})
        pagination = meta.get("pagination", {})
        total_pages = pagination.get("pageCount")
        if total_pages is None or page >= total_pages:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    return products


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
    except Exception as exc:
        print(f"[ERROR] Failed to fetch product page '{slug}': {exc}", file=sys.stderr)
        return None


def extract_metrics_from_html(html: str) -> Dict[str, Optional[float]]:
    """Extract metrics like price, rating and likes from the product page."""
    price_pattern = re.compile(r'"price"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    like_pattern = re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE)
    score_pattern = re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    count_pattern = re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE)

    metrics: Dict[str, Optional[float]] = {
        "price": None,
        "num_likes": None,
        "ratings_score": None,
        "ratings_count": None,
    }

    if match := price_pattern.search(html):
        metrics["price"] = float(match.group(1))
    if match := like_pattern.search(html):
        metrics["num_likes"] = int(match.group(1))
    if match := score_pattern.search(html):
        metrics["ratings_score"] = float(match.group(1))
    if match := count_pattern.search(html):
        metrics["ratings_count"] = int(match.group(1))

    return metrics


def scrape_flowzz_products() -> List[ProductData]:
    """Collect information for every product."""
    products_info = fetch_product_list()
    results: List[ProductData] = []
    total = len(products_info)
    for idx, entry in enumerate(products_info, start=1):
        name = entry["name"]
        slug = entry["slug"]
        url = PRODUCT_PAGE_URL.format(slug=slug)
        print(f"Processing {idx}/{total}: {name} ({slug})")
        html = fetch_product_page(slug)
        if not html:
            results.append(
                ProductData(
                    name=name,
                    slug=slug,
                    url=url,
                    price=None,
                    num_likes=None,
                    ratings_score=None,
                    ratings_count=None,
                )
            )
            continue

        metrics = extract_metrics_from_html(html)
        results.append(
            ProductData(
                name=name,
                slug=slug,
                url=url,
                price=metrics.get("price"),
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
            )
        )
        time.sleep(REQUEST_DELAY)
    return results


def save_results(products: List[ProductData]) -> None:
    """Save collected product information to JSON and CSV files."""
    data = [p.as_dict() for p in products]
    with OUTPUT_JSON.open("w", encoding="utf-8") as f_json:
        json.dump(data, f_json, indent=2, ensure_ascii=False)

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f_csv:
        writer = csv.DictWriter(
            f_csv,
            fieldnames=[
                "name",
                "slug",
                "url",
                "price",
                "num_likes",
                "ratings_score",
                "ratings_count",
            ],
        )
        writer.writeheader()
        for row in data:
            writer.writerow(row)


def print_rankings(products: List[ProductData]) -> None:
    """Print simple ranking tables for rating and price."""

    by_rating = sorted(
        products,
        key=lambda p: (
            -(p.ratings_score if p.ratings_score is not None else -1.0),
            -(p.ratings_count if p.ratings_count is not None else 0),
            p.name.lower(),
        ),
    )

    by_price = sorted(
        [p for p in products if p.price is not None], key=lambda p: p.price
    )

    def print_table(title: str, items: List[ProductData], metric: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<50} | {metric.title():>12} | URL"
        print(header)
        print("-" * len(header))
        for rank, prod in enumerate(items, start=1):
            value = getattr(prod, metric)
            value_str = f"{value}" if value is not None else "N/A"
            print(
                f"{rank:>4} | {prod.name:<50} | {value_str:>12} | {prod.url}"
            )

    print_table("Products nach Bewertung (absteigend)", by_rating, "ratings_score")
    if by_price:
        print_table("Preiswerteste Produkte", by_price, "price")


def main() -> None:
    products = scrape_flowzz_products()
    save_results(products)
    print_rankings(products)


if __name__ == "__main__":
    main()

