# -*- coding: utf-8 -*-
"""Advanced Flowzz Product Scraper
---------------------------------

This script retrieves information about all cannabis products listed on
``flowzz.com`` and stores the results in both JSON and CSV format. It
uses Flowzz's public CMS API to obtain a list of product slugs and then
fetches each corresponding product page to extract useful statistics such
as rating, number of likes and (if available) price information.

The collected data are then sorted and written to ``products.json`` and
``products.csv``.  Additionally, a human readable ranking is printed to
the console.

Because Flowzz changes its website from time to time, the scraping logic
is implemented defensively – missing fields simply result in ``None``
values rather than aborting the process.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import requests

CMS_PRODUCT_URL = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"
REQUEST_DELAY = 0.5  # seconds between requests


@dataclass
class ProductData:
    """Container for product statistics."""

    name: str
    slug: str
    url: str
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]
    price: Optional[float]

    def to_dict(self) -> Dict[str, Optional[str]]:
        d = asdict(self)
        return d


def fetch_product_list() -> List[Dict[str, str]]:
    """Fetch all products from the CMS API."""

    products: List[Dict[str, str]] = []
    page = 1
    page_size = 100

    while True:
        params = {
            "pagination[page]": page,
            "pagination[pageSize]": page_size,
        }
        try:
            resp = requests.get(CMS_PRODUCT_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[ERROR] Failed to fetch product list on page {page}: {exc}", file=sys.stderr)
            break

        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            break

        for entry in entries:
            if isinstance(entry, dict):
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
    """Extract rating, likes and price from the product page HTML."""

    num_likes_pattern = re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE)
    ratings_score_pattern = re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    ratings_count_pattern = re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE)
    price_pattern = re.compile(r'"price"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)

    metrics: Dict[str, Optional[float]] = {
        "num_likes": None,
        "ratings_score": None,
        "ratings_count": None,
        "price": None,
    }

    match = num_likes_pattern.search(html)
    if match:
        metrics["num_likes"] = int(match.group(1))

    match = ratings_score_pattern.search(html)
    if match:
        metrics["ratings_score"] = float(match.group(1))

    match = ratings_count_pattern.search(html)
    if match:
        metrics["ratings_count"] = int(match.group(1))

    match = price_pattern.search(html)
    if match:
        metrics["price"] = float(match.group(1))

    return metrics


def scrape_products() -> List[ProductData]:
    """Retrieve all product information from Flowzz."""

    product_list = fetch_product_list()
    results: List[ProductData] = []
    total = len(product_list)

    for idx, entry in enumerate(product_list, start=1):
        name = entry["name"]
        slug = entry["slug"]
        print(f"Processing {idx}/{total}: {name} ({slug})")
        html = fetch_product_page(slug)
        if not html:
            results.append(
                ProductData(name=name, slug=slug, url=PRODUCT_PAGE_URL.format(slug=slug),
                             num_likes=None, ratings_score=None, ratings_count=None, price=None)
            )
            continue
        metrics = extract_metrics_from_html(html)
        results.append(
            ProductData(
                name=name,
                slug=slug,
                url=PRODUCT_PAGE_URL.format(slug=slug),
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
                price=metrics.get("price"),
            )
        )
        time.sleep(REQUEST_DELAY)

    return results


def save_results(products: List[ProductData], json_path: str = "products.json", csv_path: str = "products.csv") -> None:
    """Save the scraped product data to JSON and CSV files."""

    with open(json_path, "w", encoding="utf-8") as f_json:
        json.dump([p.to_dict() for p in products], f_json, ensure_ascii=False, indent=2)

    with open(csv_path, "w", newline="", encoding="utf-8") as f_csv:
        writer = csv.DictWriter(f_csv, fieldnames=[
            "name", "slug", "url", "num_likes", "ratings_score", "ratings_count", "price"])
        writer.writeheader()
        for product in products:
            writer.writerow(product.to_dict())


def print_rankings(products: List[ProductData]) -> None:
    """Print rankings sorted by rating, likes and price."""

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

    by_price = [p for p in products if p.price is not None]
    by_price.sort(key=lambda p: p.price)

    def print_table(title: str, items: List[ProductData], metric_key: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<40} | {metric_key.replace('_', ' ').title():>12} | URL"
        print(header)
        print("-" * len(header))
        for rank, prod in enumerate(items, start=1):
            metric_value = getattr(prod, metric_key)
            metric_str = f"{metric_value}" if metric_value is not None else "N/A"
            print(f"{rank:>4} | {prod.name:<40} | {metric_str:>12} | {prod.url}")

    print_table("Products by Rating (desc)", by_rating, "ratings_score")
    print_table("Products by Likes (desc)", by_likes, "num_likes")
    if by_price:
        print_table("Products by Price (asc)", by_price, "price")


def main() -> None:
    products = scrape_products()
    save_results(products)
    print_rankings(products)


if __name__ == "__main__":
    main()
