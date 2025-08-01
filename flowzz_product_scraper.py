"""
flowzz_product_scraper.py
==========================

This script interacts with the public Flowzz.com API to download
information about all cannabis flower products ("Blütensorten") and
produce a sortable overview. The script performs two stages:

1.  It first retrieves a paginated list of all flowers from the
    `/api/v1/views/flowers` endpoint. Each page contains basic
    information such as the product name, THC/CBD content, rating
    score and count, minimum and maximum price and a URL slug. The
    pagination metadata indicates the total number of pages, so the
    script automatically loops through all pages to build a complete
    catalogue【844501064273002†L136-L160】.

2.  For each product in the catalogue, the script fetches the
    corresponding detail endpoint (`/api/v1/views/flowers/<slug>`) to
    obtain the number of likes (`num_likes`) for that product.  The
    detail endpoint exposes the `num_likes` field, which is not
    available on the listing endpoint【253163719721043†L58-L62】【483925897691346†L130-L133】.

After aggregating all data, the script constructs a Pandas
DataFrame containing the following fields for each product:

* ``id`` – Flowzz internal identifier.
* ``name`` – product name.
* ``thc`` – THC percentage.
* ``cbd`` – CBD percentage.
* ``ratings_score`` – average star rating (0–5).
* ``ratings_count`` – number of ratings.
* ``num_likes`` – number of likes (from the detail endpoint).
* ``min_price`` – lowest listed price per gram.
* ``max_price`` – highest listed price per gram.
* ``slug`` – URL slug for the product.
* ``product_link`` – full URL to the product page on flowzz.com.

The script sorts this DataFrame twice: first by likes in descending
order and then by rating score in descending order.  It prints both
sorted tables to stdout and also writes them to CSV files for later
analysis.  When run on a networked machine without API restrictions,
the script can take several minutes to complete because it must call
the detail endpoint for every product.  To avoid triggering Flowzz
rate‑limits, the script includes a small delay between requests.

Usage:

```
python flowzz_product_scraper.py
```

Dependencies:

* requests
* pandas

Install dependencies via pip if necessary:

```
pip install requests pandas
```

"""

import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional

import requests
import pandas as pd


API_BASE = "https://flowzz.com/api/v1/views/flowers"


@dataclass
class ProductSummary:
    """Represents a product entry from the listing endpoint."""

    id: int
    name: str
    thc: Optional[float]
    cbd: Optional[float]
    ratings_score: Optional[float]
    ratings_count: Optional[int]
    min_price: Optional[float]
    max_price: Optional[float]
    slug: str


@dataclass
class ProductDetails(ProductSummary):
    """Extends ProductSummary with likes and computed link."""

    num_likes: Optional[int]
    product_link: str


def fetch_listing(session: requests.Session, page: int, page_size: int = 100) -> dict:
    """
    Fetch a single page of the flowers listing.

    Parameters
    ----------
    session: requests.Session
        A requests session for connection pooling.
    page: int
        Page number to fetch (1‑indexed).
    page_size: int, optional
        Number of items per page.  The extension uses 30 by default
        but a larger value reduces the number of HTTP requests.

    Returns
    -------
    dict
        Decoded JSON response containing product data and pagination
        metadata.
    """
    url = (
        f"{API_BASE}?pagination[page]={page}"
        f"&pagination[pageSize]={page_size}&avail=0"
    )
    response = session.get(url)
    response.raise_for_status()
    return response.json()


def fetch_all_products(
    page_size: int = 100, delay: float = 0.5
) -> List[ProductSummary]:
    """
    Retrieve all flower products from Flowzz.

    The function iteratively queries each page of the listing endpoint
    until all products have been collected.  A short delay between
    requests can be configured to be courteous towards Flowzz's
    servers.

    Parameters
    ----------
    page_size: int
        Number of items per page to request.  Values around 100
        minimise the number of pages without risking an overly large
        response.
    delay: float
        Delay in seconds between successive HTTP requests.

    Returns
    -------
    List[ProductSummary]
        A list of ProductSummary objects representing all products.
    """
    session = requests.Session()
    # Fetch the first page to determine total pages
    first_page = fetch_listing(session, 1, page_size=page_size)
    data = first_page.get("data", {})
    products_raw = data.get("data", [])
    meta = data.get("meta", {})
    pagination = meta.get("pagination", {})
    total_pages = pagination.get("pageCount", 1)

    products: List[ProductSummary] = []
    for item in products_raw:
        products.append(
            ProductSummary(
                id=item.get("id"),
                name=item.get("name"),
                thc=item.get("thc"),
                cbd=item.get("cbd"),
                ratings_score=item.get("ratings_score"),
                ratings_count=item.get("ratings_count"),
                min_price=item.get("min_price"),
                max_price=item.get("max_price"),
                slug=item.get("url"),
            )
        )

    # Loop through remaining pages
    for page in range(2, total_pages + 1):
        time.sleep(delay)
        resp = fetch_listing(session, page, page_size=page_size)
        data = resp.get("data", {})
        items = data.get("data", [])
        for item in items:
            products.append(
                ProductSummary(
                    id=item.get("id"),
                    name=item.get("name"),
                    thc=item.get("thc"),
                    cbd=item.get("cbd"),
                    ratings_score=item.get("ratings_score"),
                    ratings_count=item.get("ratings_count"),
                    min_price=item.get("min_price"),
                    max_price=item.get("max_price"),
                    slug=item.get("url"),
                )
            )

    return products


def fetch_product_likes(session: requests.Session, slug: str) -> Optional[int]:
    """
    Retrieve the number of likes for a specific product.

    The detail endpoint exposes a ``num_likes`` field, which
    corresponds to the number of likes shown on the product page
    【253163719721043†L58-L62】.

    Parameters
    ----------
    session: requests.Session
        A requests session for connection pooling.
    slug: str
        The URL slug of the product.

    Returns
    -------
    Optional[int]
        The ``num_likes`` value, or ``None`` if not found.
    """
    url = f"{API_BASE}/{slug}"
    resp = session.get(url)
    # If the request fails, propagate the error to the caller
    resp.raise_for_status()
    data = resp.json()
    # Drill down into the nested JSON to extract num_likes
    attributes = data.get("data", {}).get("attributes", {})
    likes = data.get("data", {}).get("num_likes")
    # Older API versions nest num_likes inside the top level of the response
    if likes is not None:
        return likes
    # Fallback if structure differs
    return attributes.get("num_likes")


def enrich_products_with_likes(
    products: List[ProductSummary], delay: float = 0.5
) -> List[ProductDetails]:
    """
    Fetch likes for every product in a list and return enriched objects.

    Parameters
    ----------
    products: List[ProductSummary]
        Basic product information from the listing.
    delay: float
        Delay in seconds between successive detail requests.

    Returns
    -------
    List[ProductDetails]
        Products extended with ``num_likes`` and ``product_link``.
    """
    session = requests.Session()
    enriched: List[ProductDetails] = []
    for idx, product in enumerate(products, 1):
        try:
            likes = fetch_product_likes(session, product.slug)
        except requests.HTTPError as e:
            # In case of failure, record None for likes and continue
            likes = None
        enriched.append(
            ProductDetails(
                **asdict(product),
                num_likes=likes,
                product_link=f"https://flowzz.com/product/{product.slug}",
            )
        )
        # Optional delay to avoid overloading the API
        time.sleep(delay)
    return enriched


def build_dataframe(products: List[ProductDetails]) -> pd.DataFrame:
    """
    Convert a list of product objects into a Pandas DataFrame.

    Parameters
    ----------
    products: List[ProductDetails]
        The enriched product data.

    Returns
    -------
    pandas.DataFrame
        DataFrame containing all products with relevant fields.
    """
    records = []
    for p in products:
        record = {
            "id": p.id,
            "name": p.name,
            "thc": p.thc,
            "cbd": p.cbd,
            "ratings_score": p.ratings_score,
            "ratings_count": p.ratings_count,
            "num_likes": p.num_likes,
            "min_price": p.min_price,
            "max_price": p.max_price,
            "slug": p.slug,
            "product_link": p.product_link,
        }
        records.append(record)
    return pd.DataFrame(records)


def fetch_product_details(session: requests.Session, slug: str) -> ProductDetails:
    """Download detailed information for a single product."""
    url = f"{API_BASE}/{slug}"
    resp = session.get(url)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    attrs = data.get("attributes", {})
    likes = data.get("num_likes")
    if likes is None:
        likes = attrs.get("num_likes")
    return ProductDetails(
        id=data.get("id"),
        name=attrs.get("name"),
        thc=attrs.get("thc"),
        cbd=attrs.get("cbd"),
        ratings_score=attrs.get("ratings_score"),
        ratings_count=attrs.get("ratings_count"),
        min_price=attrs.get("min_price"),
        max_price=attrs.get("max_price"),
        slug=slug,
        num_likes=likes,
        product_link=f"https://flowzz.com/product/{slug}",
    )


def fetch_products_by_slugs(slugs: List[str], delay: float = 0.5) -> List[ProductDetails]:
    """Return detailed product data for a list of slugs."""
    session = requests.Session()
    results: List[ProductDetails] = []
    for slug in slugs:
        try:
            details = fetch_product_details(session, slug)
        except requests.HTTPError:
            continue
        results.append(details)
        time.sleep(delay)
    return results


def scrape_by_slugs(slugs: List[str], delay: float = 0.5) -> pd.DataFrame:
    """Convenience wrapper returning a DataFrame for selected slugs."""
    products = fetch_products_by_slugs(slugs, delay=delay)
    return build_dataframe(products)


def scrape_all(page_size: int = 100, delay: float = 0.1) -> pd.DataFrame:
    """Convenience wrapper returning a DataFrame with all product data."""
    products = fetch_all_products(page_size=page_size, delay=delay)
    enriched = enrich_products_with_likes(products, delay=delay)
    return build_dataframe(enriched)


def main() -> None:
    """Command line interface for scraping and exporting product data."""
    print("Fetching product listing…")
    df = scrape_all(page_size=100, delay=0.1)

    # Sort by likes (descending) and display
    df_by_likes = df.sort_values(
        by=["num_likes", "ratings_score"], ascending=[False, False]
    )
    print("\nTop products sorted by likes:\n")
    print(df_by_likes.head(50).to_string(index=False))
    df_by_likes.to_csv("flowzz_products_by_likes.csv", index=False)

    # Sort by ratings_score (descending) and display
    df_by_rating = df.sort_values(
        by=["ratings_score", "ratings_count"], ascending=[False, False]
    )
    print("\nTop products sorted by star rating:\n")
    print(df_by_rating.head(50).to_string(index=False))
    df_by_rating.to_csv("flowzz_products_by_rating.csv", index=False)

    print(
        "\nData exported to 'flowzz_products_by_likes.csv' and 'flowzz_products_by_rating.csv'."
    )
