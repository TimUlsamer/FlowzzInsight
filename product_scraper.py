# New script to fetch and rank Flowzz product data

import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


# Delay between requests so we are nice to Flowzz's servers
REQUEST_DELAY = 0.5

# API endpoints used for product listing and detail pages
CMS_PRODUCT_API = "https://cms.flowzz.com/api/products"
PRODUCT_PAGE_URL = "https://flowzz.com/product/{slug}"


@dataclass
class ProductData:
    """Information scraped for a single product."""

    name: str
    slug: str
    url: str
    num_likes: Optional[int]
    ratings_score: Optional[float]
    ratings_count: Optional[int]
    price_eur: Optional[float]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "url": self.url,
            "num_likes": self.num_likes,
            "ratings_score": self.ratings_score,
            "ratings_count": self.ratings_count,
            "price_eur": self.price_eur,
        }


def fetch_product_list() -> List[Dict[str, str]]:
    """Retrieve all products via the CMS API."""
    products: List[Dict[str, str]] = []
    page = 1
    size = 100
    while True:
        params = {
            "pagination[page]": page,
            "pagination[pageSize]": size,
        }
        try:
            resp = requests.get(CMS_PRODUCT_API, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[ERROR] Unable to fetch product list on page {page}: {exc}", file=sys.stderr)
            break

        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            break
        for entry in entries:
            name = ""
            slug = ""
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("attributes", {}).get("name") or ""
                slug = entry.get("url") or entry.get("attributes", {}).get("url") or ""
            if name and slug:
                products.append({"name": name, "slug": slug})
        meta = data.get("meta", {}).get("pagination", {})
        if not meta or page >= meta.get("pageCount", page):
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


def _search_json_for_keys(obj: Any, keys: List[str]) -> Optional[Dict[str, Any]]:
    """Recursively search nested JSON object for dictionary containing keys."""
    if isinstance(obj, dict):
        if all(k in obj for k in keys):
            return obj
        for value in obj.values():
            found = _search_json_for_keys(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _search_json_for_keys(item, keys)
            if found:
                return found
    return None


def extract_metrics_from_html(html: str) -> Dict[str, Optional[Any]]:
    """Parse embedded JSON from a product page and extract metrics."""
    result: Dict[str, Optional[Any]] = {
        "num_likes": None,
        "ratings_score": None,
        "ratings_count": None,
        "price_eur": None,
    }
    # Look for Next.js data
    data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not data_match:
        return result
    try:
        data = json.loads(data_match.group(1))
    except Exception:
        return result

    # Attempt to find product attributes in the JSON structure
    keys = ["num_likes", "ratings_score", "ratings_count"]
    info = _search_json_for_keys(data, keys)
    if info:
        result["num_likes"] = info.get("num_likes")
        result["ratings_score"] = info.get("ratings_score")
        result["ratings_count"] = info.get("ratings_count")

    # Try several candidate keys for price
    price_keys = ["price", "min_price", "lowest_price", "price_eur"]
    for pk in price_keys:
        price = _search_json_for_keys(data, [pk])
        if price and pk in price:
            try:
                result["price_eur"] = float(price[pk])
                break
            except Exception:
                pass

    return result


def scrape_products() -> List[ProductData]:
    products_info = fetch_product_list()
    total = len(products_info)
    results: List[ProductData] = []
    for idx, entry in enumerate(products_info, start=1):
        name = entry["name"]
        slug = entry["slug"]
        url = PRODUCT_PAGE_URL.format(slug=slug)
        print(f"Processing {idx}/{total}: {name}")
        html = fetch_product_page(slug)
        if not html:
            results.append(ProductData(name, slug, url, None, None, None, None))
            continue
        metrics = extract_metrics_from_html(html)
        results.append(
            ProductData(
                name=name,
                slug=slug,
                url=url,
                num_likes=metrics.get("num_likes"),
                ratings_score=metrics.get("ratings_score"),
                ratings_count=metrics.get("ratings_count"),
                price_eur=metrics.get("price_eur"),
            )
        )
        time.sleep(REQUEST_DELAY)
    return results


def save_results(products: List[ProductData], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.as_dict() for p in products], f, ensure_ascii=False, indent=2)


def print_rankings(products: List[ProductData]) -> None:
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

    by_price = sorted(
        products,
        key=lambda p: (
            p.price_eur if p.price_eur is not None else float("inf"),
            p.name.lower(),
        ),
    )

    def print_table(title: str, items: List[ProductData], metric: str):
        print("\n" + title)
        print("=" * len(title))
        header = f"{'Rank':>4} | {'Product':<40} | {metric.replace('_',' ').title():>12} | {'Link'}"
        print(header)
        print("-" * len(header))
        for rank, item in enumerate(items, 1):
            value = getattr(item, metric)
            value_str = f"{value}" if value is not None else "N/A"
            print(f"{rank:>4} | {item.name:<40} | {value_str:>12} | {item.url}")

    print_table("Products by Rating", by_rating, "ratings_score")
    print_table("Products by Likes", by_likes, "num_likes")
    print_table("Products by Lowest Price", by_price, "price_eur")


def main() -> None:
    products = scrape_products()
    save_results(products, "products.json")
    print_rankings(products)


if __name__ == "__main__":
    main()
