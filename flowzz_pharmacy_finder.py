# flowzz_pharmacy_finder.py
"""Utility to find pharmacies offering specific cannabis strains."""

from dataclasses import dataclass
from typing import List, Dict

import requests
import pandas as pd

import flowzz_product_scraper as scraper

VENDOR_API = "https://flowzz.com/api/vendor?t=2&id={id}"

@dataclass
class VendorInfo:
    name: str
    price: float
    website: str | None


def fetch_vendors_for_strain(strain_id: int) -> List[VendorInfo]:
    """Return a list of vendors offering a given strain."""
    url = VENDOR_API.format(id=strain_id)
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()

    vendors = []
    price_flowers = (
        data.get("message", {}).get("data", {}).get("priceFlowers", {}).get("data", [])
    )
    for item in price_flowers:
        attr = item.get("attributes", {})
        avail = attr.get("availibility")
        if avail not in (1, 2):
            continue
        vendor_data = attr.get("vendor", {}).get("data", {})
        vendor_attr = vendor_data.get("attributes", {})
        vendors.append(
            VendorInfo(
                name=vendor_attr.get("name"),
                price=float(attr.get("price")),
                website=vendor_attr.get("website"),
            )
        )
    return vendors


def find_common_vendors(strain_ids: List[int]) -> pd.DataFrame:
    """Return vendors that offer all given strains with price summary."""
    vendor_maps: List[Dict[str, VendorInfo]] = []
    for sid in strain_ids:
        vendors = fetch_vendors_for_strain(sid)
        vmap = {v.name: v for v in vendors}
        vendor_maps.append(vmap)

    if not vendor_maps:
        return pd.DataFrame()

    common_names = set(vendor_maps[0].keys())
    for vmap in vendor_maps[1:]:
        common_names &= set(vmap.keys())

    rows = []
    for name in common_names:
        total = 0.0
        websites = []
        prices = []
        for vmap in vendor_maps:
            v = vmap[name]
            total += v.price
            prices.append(v.price)
            if v.website:
                websites.append(v.website)
        rows.append({"vendor": name, "total_price": total, **{f"price_{i+1}": p for i, p in enumerate(prices)}, "websites": ", ".join(websites)})

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("total_price")
    return df


def main() -> None:
    print("Fetching strain catalogue…")
    products = scraper.fetch_all_products(page_size=100, delay=0.1)
    options = {p.name: p.id for p in products}

    print("Enter up to 3 strain names (exact as listed). Leave blank to finish:")
    selected_ids = []
    for i in range(3):
        name = input(f"Strain {i+1}: ").strip()
        if not name:
            break
        sid = options.get(name)
        if sid is None:
            print("Unknown strain. Try again.")
            continue
        selected_ids.append(sid)
    if not selected_ids:
        print("No strains selected.")
        return

    print("Finding pharmacies…")
    df = find_common_vendors(selected_ids)
    if df.empty:
        print("No pharmacy carries all selected strains.")
        return
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()

