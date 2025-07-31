"""Flowzz Product Scraper
-----------------------

This script collects statistics about specific cannabis products listed on
`flowzz.com`. It uses the public CMS and product pages to gather
information and saves the results for later analysis.

Features
========
* Fetches all product slugs from the Flowzz CMS API.
* Extracts metrics from each product page (rating, likes, price).
* Saves raw data to `products.json` and a summary table to `products.csv`.
* Prints ranked lists of products by rating, likes and price.

The scraper relies only on the ``requests`` library and the Python standard
library so it can run in restricted environments. Network failures or missing
fields are handled gracefully.

Note
----
Access to ``flowzz.com`` may be restricted. In such cases the script will
report errors while attempting to download data. The overall structure,
including file output, remains intact so the script can be adapted once
network access is available.
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

# Polite delay between HTTP requests (seconds)
REQUEST_DELAY = 0.5

# API endpoints
CMS_PRODUCT_URL = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"


@dataclass
class ProductData:
    """Container for extracted product information."""

    name: str
    slug: str
    strain: Optional[str]
    brand: Optional[str]
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]
    price_eur: Optional[float]


def fetch_product_list() -> List[Dict[str, str]]:
    """Retrieve all product entries from the CMS API."""
    products: List[Dict[str, str]] = []
    page = 1
    page_size = 100
    while True:
        params = {"pagination[page]": page, "pagination[pageSize]": page_size}
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
            attr = entry.get("attributes") or entry
            name = attr.get("name") or ""
            slug = attr.get("url") or ""
            strain = attr.get("strain_name")
            brand = attr.get("brand")
            if name and slug:
                products.append({"name": name, "slug": slug, "strain": strain, "brand": brand})
        meta = data.get("meta", {}).get("pagination", {})
        total_pages = meta.get("pageCount")
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
    """Extract relevant metrics from a product page."""
    metrics: Dict[str, Optional[float]] = {
        "num_likes": None,
        "ratings_score": None,
        "ratings_count": None,
        "price_eur": None,
    }

    like_pattern = re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE)
    score_pattern = re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    count_pattern = re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE)
    price_pattern = re.compile(r'"price"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)

    if match := like_pattern.search(html):
        metrics["num_likes"] = int(match.group(1))
    if match := score_pattern.search(html):
        metrics["ratings_score"] = float(match.group(1))
    if match := count_pattern.search(html):
        metrics["ratings_count"] = int(match.group(1))
    if match := price_pattern.search(html):
        metrics["price_eur"] = float(match.group(1))

    return metrics


def scrape_products() -> List[ProductData]:
    """Collect information for all products."""
    products_info = fetch_product_list()
    results: List[ProductData] = []
    total = len(products_info)
    for idx, entry in enumerate(products_info, start=1):
        name = entry["name"]
        slug = entry["slug"]
        strain = entry.get("strain")
        brand = entry.get("brand")
        print(f"Processing {idx}/{total}: {name} ({slug})")
        html = fetch_product_page(slug)
        if not html:
            results.append(
                ProductData(
                    name=name,
                    slug=slug,
                    strain=strain,
                    brand=brand,
                    num_likes=None,
                    ratings_score=None,
                    ratings_count=None,
                    price_eur=None,
                )
            )
            continue
        metrics = extract_metrics_from_html(html)
        results.append(
            ProductData(
                name=name,
                slug=slug,
                strain=strain,
                brand=brand,
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
                price_eur=metrics.get("price_eur"),
            )
        )
        time.sleep(REQUEST_DELAY)
    return results


def save_results(products: List[ProductData]) -> None:
    """Save scraped product data to JSON and CSV files."""
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)
    with open("products.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "name",
            "slug",
            "strain",
            "brand",
            "num_likes",
            "ratings_score",
            "ratings_count",
            "price_eur",
            "url",
        ])
        for p in products:
            writer.writerow([
                p.name,
                p.slug,
                p.strain or "",
                p.brand or "",
                p.num_likes if p.num_likes is not None else "",
                p.ratings_score if p.ratings_score is not None else "",
                p.ratings_count if p.ratings_count is not None else "",
                p.price_eur if p.price_eur is not None else "",
                PRODUCT_PAGE_URL.format(slug=p.slug),
            ])


def print_rankings(products: List[ProductData]) -> None:
    """Display ranked lists of products."""
    def safe_metric(value, default):
        return value if value is not None else default

    by_rating = sorted(
        products,
        key=lambda p: (
            -safe_metric(p.ratings_score, -1.0),
            -safe_metric(p.ratings_count, 0),
            p.name.lower(),
        ),
    )

    by_likes = sorted(
        products,
        key=lambda p: (-safe_metric(p.num_likes, -1), p.name.lower()),
    )

    by_price = sorted(
        [p for p in products if p.price_eur is not None],
        key=lambda p: p.price_eur,
    )

    def print_table(title: str, entries: List[ProductData], metric_key: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<50} | {metric_key.replace('_', ' ').title():>12}"
        print(header)
        print("-" * len(header))
        for rank, p in enumerate(entries, start=1):
            metric_value = getattr(p, metric_key)
            metric_str = f"{metric_value}" if metric_value is not None else "N/A"
            print(f"{rank:>4} | {p.name:<50} | {metric_str:>12}")

    print_table("Produkte nach Bewertung (absteigend)", by_rating, "ratings_score")
    print_table("Produkte nach Likes (absteigend)", by_likes, "num_likes")
    if by_price:
        print_table("Produkte nach Preis (aufsteigend)", by_price, "price_eur")


def main() -> None:
    products = scrape_products()
    save_results(products)
    print_rankings(products)


if __name__ == "__main__":
    main()
