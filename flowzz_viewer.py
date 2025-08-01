import os
import pandas as pd
import streamlit as st

import flowzz_product_scraper as scraper
from flowzz_pharmacy_helper import pharmacies_with_all_strains

CSV_PATH = "flowzz_products_by_likes.csv"  # Passe ggf. an
MAX_SELECTION = 3  # max strains to search pharmacies for

st.set_page_config(page_title="Flowzz Produktübersicht", layout="wide")
st.title("Interaktive Übersicht: Flowzz Cannabisprodukte")

@st.cache_data
def load_data(path):
    return pd.read_csv(path)

@st.cache_data(show_spinner=False)
def scrape_data() -> pd.DataFrame:
    """Download products from Flowzz and return as DataFrame."""
    products = scraper.fetch_all_products(page_size=100, delay=0.1)
    enriched = scraper.enrich_products_with_likes(products, delay=0.1)
    return scraper.build_dataframe(enriched)

if "df" not in st.session_state:
    st.session_state["df"] = load_data(CSV_PATH)

if st.button("Daten aktualisieren"):
    with st.spinner("Aktualisiere Daten..."):
        new_df = scrape_data()
    st.session_state["df"] = new_df
    new_df.to_csv(CSV_PATH, index=False)

df = st.session_state["df"]

# -------- Filter in der Sidebar --------
st.sidebar.header("Filter")

# Produktsuche
name_filter = st.sidebar.text_input("Produktsuche (Name)")

# THC Filter
min_thc, max_thc = float(df["thc"].min()), float(df["thc"].max())
thc_slider = st.sidebar.slider(
    "THC-Gehalt (%)", min_thc, max_thc, (min_thc, max_thc)
)

# CBD Filter
min_cbd, max_cbd = float(df["cbd"].min()), float(df["cbd"].max())
cbd_slider = st.sidebar.slider(
    "CBD-Gehalt (%)", min_cbd, max_cbd, (min_cbd, max_cbd)
)

# Ratings Score Filter
min_rating, max_rating = float(df["ratings_score"].min()), float(df["ratings_score"].max())
rating_slider = st.sidebar.slider(
    "Bewertung (Sterne)", min_rating, max_rating, (min_rating, max_rating)
)

# Ratings Count Filter
min_count, max_count = int(df["ratings_count"].min()), int(df["ratings_count"].max())
count_slider = st.sidebar.slider(
    "Anzahl Bewertungen", min_count, max_count, (min_count, max_count)
)

# Likes Filter
min_likes, max_likes = int(df["num_likes"].min()), int(df["num_likes"].max())
likes_slider = st.sidebar.slider(
    "Anzahl Likes", min_likes, max_likes, (min_likes, max_likes)
)

# Preis Filter
min_price, max_price = float(df["min_price"].min()), float(df["max_price"].max())
price_slider = st.sidebar.slider(
    "Preis pro Gramm (€)", min_price, max_price, (min_price, max_price)
)

# --------- Sortieren ---------
sort_col = st.sidebar.selectbox(
    "Sortiere nach", options=df.columns, index=list(df.columns).index("num_likes")
)
ascending = st.sidebar.checkbox("Aufsteigend sortieren", value=False)

# --------- Anwenden der Filter ----------
filtered_df = df.copy()

# Name-Filter
if name_filter:
    filtered_df = filtered_df[filtered_df["name"].str.contains(name_filter, case=False, na=False)]

# THC, CBD, Rating, Rating Count, Likes, Preis-Filter
filtered_df = filtered_df[
    filtered_df["thc"].between(*thc_slider)
    & filtered_df["cbd"].between(*cbd_slider)
    & filtered_df["ratings_score"].between(*rating_slider)
    & filtered_df["ratings_count"].between(*count_slider)
    & filtered_df["num_likes"].between(*likes_slider)
    & filtered_df["min_price"].between(*price_slider)
]

# Sortieren
filtered_df = filtered_df.sort_values(by=sort_col, ascending=ascending)

# -------- Anzeige ---------
st.write(f"**{len(filtered_df)} Produkte gefunden**")

if "selected_ids" not in st.session_state:
    st.session_state["selected_ids"] = []

display_df = filtered_df.copy()
display_df["Auswählen"] = display_df["id"].isin(st.session_state["selected_ids"])
edited_df = st.data_editor(
    display_df,
    column_config={
        "Auswählen": st.column_config.CheckboxColumn("Für Suche auswählen", width="small")
    },
    disabled=[c for c in display_df.columns if c != "Auswählen"],
    hide_index=True,
    use_container_width=True,
    key="product_editor",
)

st.session_state["selected_ids"] = (
    edited_df.loc[edited_df["Auswählen"], "id"].tolist()
)

# Download
st.download_button(
    "CSV exportieren", filtered_df.to_csv(index=False), "flowzz_export.csv", "text/csv"
)

# -------- Pharmacy Finder ---------
st.header("Apotheken Finder")

strain_options = df[["id", "name"]].drop_duplicates().sort_values("name")
selected_ids = st.session_state.get("selected_ids", [])
selected_names = [
    strain_options.loc[strain_options["id"] == sid, "name"].values[0]
    for sid in selected_ids
]

if selected_names:
    st.write("Ausgewählt:", ", ".join(selected_names))
    if len(selected_ids) > MAX_SELECTION:
        st.error(f"Bitte maximal {MAX_SELECTION} Sorten auswählen.")
    elif st.button("Apotheken suchen"):
        with st.spinner("Suche Apotheken..."):
            results = pharmacies_with_all_strains(selected_ids)
        if results:
            display_rows = []
            for entry in results:
                row = {
                    "Apotheke": entry["pharmacy"],
                    "Website": entry["website"],
                    "Gesamtpreis": entry["total"],
                }
                for sid in selected_ids:
                    name = strain_options.loc[strain_options["id"] == sid, "name"].values[0]
                    row[name] = entry["prices"][sid]
                display_rows.append(row)
            res_df = pd.DataFrame(display_rows).sort_values("Gesamtpreis")
            st.write(f"**{len(res_df)} Apotheken gefunden**")
            st.dataframe(res_df, use_container_width=True)
        else:
            st.write("Keine Apotheke führt alle ausgewählten Sorten.")
