"""Advanced Flowzz Product Scraper
---------------------------------

This script retrieves all cannabis product listings from ``flowzz.com`` and
collects several metrics from each product page. Results are saved to JSON and
CSV files and summary tables are printed to the console.

The program works in three steps:

1. **Query product slugs via the CMS** – It uses the public ``cms.flowzz.com``
   API to obtain all product slugs and names.
2. **Scrape the product pages** – For every slug the corresponding product
   page is downloaded and metrics such as price, rating and number of likes are
   extracted from the embedded JSON data.
3. **Rank and store** – The products are sorted by rating and price.  The
   tables are printed and the full dataset is written to ``products.json`` and
   ``products.csv`` for later use.

Note that the structure of Flowzz's pages may change at any time.  The regular
expressions in this script are based on the current markup and may require
adjustments in the future.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import requests

# Delay between HTTP requests so we do not hammer the server.
REQUEST_DELAY = 0.5

# CMS and product page endpoints.  ``{slug}`` will be replaced with the product
# slug returned by the CMS.
CMS_PRODUCTS_URL = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"


@dataclass
class ProductData:
    """Container for a product entry."""

    name: str
    slug: str
    url: str
    price: Optional[float]
    num_likes: Optional[int]
    rating_score: Optional[float]
    rating_count: Optional[int]


def fetch_product_list() -> List[Dict[str, str]]:
    """Return all products as ``{"name": ..., "slug": ...}`` dictionaries."""

    products: List[Dict[str, str]] = []
    page = 1
    page_size = 100

    while True:
        params = {
            "pagination[page]": page,
            "pagination[pageSize]": page_size,
        }
        try:
            resp = requests.get(CMS_PRODUCTS_URL, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - network errors
            print(f"[ERROR] Failed to fetch product list on page {page}: {exc}", file=sys.stderr)
            break

        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            break

        for entry in entries:
            if not isinstance(entry, dict):
                continue
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
    """Download the HTML for a product page."""

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


def extract_metrics_from_html(html: str) -> Dict[str, Optional[float]]:
    """Return ``{"price": float, "rating_score": float, ...}`` extracted from HTML."""

    price_pattern = re.compile(r'"price"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    like_pattern = re.compile(r'"num_likes"\s*:\s*(\d+)', re.IGNORECASE)
    score_pattern = re.compile(r'"ratings_score"\s*:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    count_pattern = re.compile(r'"ratings_count"\s*:\s*(\d+)', re.IGNORECASE)

    metrics: Dict[str, Optional[float]] = {
        "price": None,
        "num_likes": None,
        "rating_score": None,
        "rating_count": None,
    }

    match = price_pattern.search(html)
    if match:
        metrics["price"] = float(match.group(1))

    match = like_pattern.search(html)
    if match:
        metrics["num_likes"] = int(match.group(1))

    match = score_pattern.search(html)
    if match:
        metrics["rating_score"] = float(match.group(1))

    match = count_pattern.search(html)
    if match:
        metrics["rating_count"] = int(match.group(1))

    return metrics


def scrape_products() -> List[ProductData]:
    """Collect data for all Flowzz products."""

    product_infos = fetch_product_list()
    results: List[ProductData] = []
    total = len(product_infos)
    for idx, entry in enumerate(product_infos, start=1):
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
                    rating_score=None,
                    rating_count=None,
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
                rating_score=metrics.get("rating_score"),
                rating_count=metrics.get("rating_count"),
            )
        )
        time.sleep(REQUEST_DELAY)
    return results


def save_results_json(products: List[ProductData], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in products], f, ensure_ascii=False, indent=2)


def save_results_csv(products: List[ProductData], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["name", "slug", "url", "price", "num_likes", "rating_score", "rating_count"]
        )
        for p in products:
            writer.writerow(
                [p.name, p.slug, p.url, p.price, p.num_likes, p.rating_score, p.rating_count]
            )


def print_ranked_tables(products: List[ProductData]) -> None:
    """Print tables sorted by rating and by price."""

    by_rating = sorted(
        products,
        key=lambda p: (
            -(p.rating_score if p.rating_score is not None else -1.0),
            -(p.rating_count if p.rating_count is not None else 0),
            p.name.lower(),
        ),
    )

    by_price = sorted(
        products,
        key=lambda p: (p.price if p.price is not None else float("inf"), p.name.lower()),
    )

    def print_table(title: str, entries: List[ProductData], metric: str) -> None:
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<40} | {metric.replace('_', ' ').title():>12} | URL"
        print(header)
        print("-" * len(header))
        for rank, prod in enumerate(entries, start=1):
            metric_val = getattr(prod, metric)
            metric_str = f"{metric_val}" if metric_val is not None else "N/A"
            print(f"{rank:>4} | {prod.name:<40} | {metric_str:>12} | {prod.url}")

    print_table("Products by Rating (desc)", by_rating, "rating_score")
    print_table("Products by Price (asc)", by_price, "price")


def main() -> None:
    products = scrape_products()
    save_results_json(products, "products.json")
    save_results_csv(products, "products.csv")
    print_ranked_tables(products)


if __name__ == "__main__":
    main()
