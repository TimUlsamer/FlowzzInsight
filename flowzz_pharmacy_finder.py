import pandas as pd
import requests
import streamlit as st

import flowzz_product_scraper as scraper

st.set_page_config(page_title="Flowzz Pharmacy Finder", layout="wide")
st.title("Pharmacy Finder")

@st.cache_data
def load_strains():
    """Return list of strains with id and name."""
    products = scraper.fetch_all_products(page_size=100, delay=0.1)
    return [{"id": p.id, "name": p.name} for p in products]

@st.cache_data
def fetch_vendors(strain_id: int):
    """Fetch vendors for a given strain via Flowzz API."""
    url = f"https://flowzz.com/api/vendor?t=2&id={strain_id}"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    entries = data.get("message", {}).get("data", {}).get("priceFlowers", {}).get("data", [])
    vendors = []
    for item in entries:
        attrs = item.get("attributes", {})
        avail = attrs.get("availibility")
        if avail in (1, 2):
            vendor_attrs = attrs.get("vendor", {}).get("data", {}).get("attributes", {})
            vendors.append({
                "name": vendor_attrs.get("name"),
                "website": vendor_attrs.get("website"),
                "price": attrs.get("price"),
            })
    return vendors

strains = load_strains()
name_to_id = {s["name"]: s["id"] for s in strains}

selected = st.multiselect(
    "Select up to 3 strains",
    options=list(name_to_id.keys()),
    max_selections=3,
)

if selected:
    vendor_sets = []
    vendor_lookup = {}
    for name in selected:
        with st.spinner(f"Fetching vendors for {name}..."):
            try:
                vendors = fetch_vendors(name_to_id[name])
            except requests.RequestException:
                st.error(f"Failed to fetch vendors for {name}")
                vendors = []
        vendor_sets.append({v["name"] for v in vendors})
        vendor_lookup[name] = {v["name"]: v for v in vendors}

    common = set.intersection(*vendor_sets) if vendor_sets else set()
    if common:
        rows = []
        for vendor in sorted(common):
            row = {"Pharmacy": vendor}
            total = 0.0
            for name in selected:
                price = vendor_lookup[name][vendor]["price"]
                row[name] = price
                total += price
            row["Total"] = total
            rows.append(row)
        rows.sort(key=lambda r: r["Total"])
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.write("No pharmacy offers all selected strains.")
