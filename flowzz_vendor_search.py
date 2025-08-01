"""Utility to find vendors stocking selected Flowzz products."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

import requests

API_BASE = "https://flowzz.com/api/v1/views/flowers"


@dataclass
class VendorInfo:
    """Map a product to the list of vendors that carry it."""

    slug: str
    vendors: List[str]


def fetch_product_vendors(session: requests.Session, slug: str) -> VendorInfo:
    """Return vendor names for a given product slug."""
    url = f"{API_BASE}/{slug}"
    resp = session.get(url)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    attributes = data.get("attributes", {})
    # The Flowzz detail endpoint lists shops under ``vendors`` or ``shops``.
    vendors = attributes.get("vendors") or attributes.get("shops") or []
    names = [v.get("name") if isinstance(v, dict) else v for v in vendors]
    return VendorInfo(slug=slug, vendors=[n for n in names if n])


def find_common_vendors(slugs: List[str]) -> Set[str]:
    """Return vendors that stock all provided products."""
    if len(slugs) == 0:
        return set()
    if len(slugs) > 3:
        raise ValueError("Only up to 3 products supported")

    session = requests.Session()
    vendor_sets: List[Set[str]] = []
    for slug in slugs:
        info = fetch_product_vendors(session, slug)
        vendor_sets.append(set(info.vendors))

    # Intersect all vendor sets
    common = vendor_sets[0]
    for s in vendor_sets[1:]:
        common &= s
    return common


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python flowzz_vendor_search.py <slug1> [<slug2> <slug3>]")
        raise SystemExit(1)
    try:
        vendors = find_common_vendors(sys.argv[1:])
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}")
        raise SystemExit(1)

    if not vendors:
        print("No vendor stocks all selected products.")
    else:
        print("Vendors stocking all products:")
        for v in sorted(vendors):
            print(f"- {v}")
