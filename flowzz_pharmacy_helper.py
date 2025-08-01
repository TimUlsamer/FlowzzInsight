import requests
from dataclasses import dataclass
from typing import List, Dict, Optional


API_VENDOR = "https://flowzz.com/api/vendor?t=2&id={id}"


@dataclass
class VendorInfo:
    name: str
    price: float
    website: Optional[str]


def fetch_vendors_for_strain(
    strain_id: int, session: Optional[requests.Session] = None
) -> List[VendorInfo]:
    """Return vendors offering a given strain with availability 1 or 2."""
    if session is None:
        session = requests.Session()
    url = API_VENDOR.format(id=strain_id)
    resp = session.get(url)
    resp.raise_for_status()
    data = resp.json()
    vendors_raw = (
        data.get("message", {}).get("data", {}).get("priceFlowers", {}).get("data", [])
    )
    vendors: List[VendorInfo] = []
    for vendor in vendors_raw:
        attrs = vendor.get("attributes", {})
        if attrs.get("availibility") not in (1, 2):
            continue
        vendor_data = attrs.get("vendor", {}).get("data", {})
        name = vendor_data.get("attributes", {}).get("name")
        website = vendor_data.get("attributes", {}).get("website")
        price = attrs.get("price")
        if name is None or price is None:
            continue
        vendors.append(VendorInfo(name=name, price=float(price), website=website))
    return vendors


def pharmacies_with_all_strains(strain_ids: List[int]) -> List[Dict[str, object]]:
    """Find pharmacies that stock all given strains."""
    session = requests.Session()
    vendor_maps = []
    for sid in strain_ids:
        vendor_list = fetch_vendors_for_strain(sid, session=session)
        vendor_maps.append({v.name: v for v in vendor_list})
    if not vendor_maps:
        return []
    common_names = set(vendor_maps[0].keys())
    for m in vendor_maps[1:]:
        common_names &= set(m.keys())
    results = []
    for name in common_names:
        total = 0.0
        prices = {}
        website = None
        for sid, m in zip(strain_ids, vendor_maps):
            v = m[name]
            prices[sid] = v.price
            total += v.price
            if website is None:
                website = v.website
        results.append(
            {"pharmacy": name, "prices": prices, "total": total, "website": website}
        )
    results.sort(key=lambda x: x["total"])
    return results
