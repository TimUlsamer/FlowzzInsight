import pandas as pd
import streamlit as st

from flowzz_product_scraper import (
    fetch_all_products,
    enrich_products_with_likes,
    build_dataframe,
)

CSV_PATH = "flowzz_products_by_likes.csv"  # Passe ggf. an

st.set_page_config(page_title="Flowzz Produktübersicht", layout="wide")
st.title("Interaktive Übersicht: Flowzz Cannabisprodukte")

@st.cache_data
def load_data(path):
    return pd.read_csv(path)

@st.cache_data
def fetch_selected(slugs):
    products = fetch_all_products(slugs=slugs)
    enriched = enrich_products_with_likes(products)
    return build_dataframe(enriched)

if "df" not in st.session_state:
    st.session_state.df = load_data(CSV_PATH)

df = st.session_state.df

# -------- Auswahl der Produkte --------
st.sidebar.header("Auswahl Produkte")
available_slugs = df["slug"].unique().tolist()
slug_select = st.sidebar.multiselect("Produkte (Slug)", options=available_slugs)
slug_text = st.sidebar.text_input("Weitere Slugs, kommagetrennt")
extra_slugs = [s.strip() for s in slug_text.split(",") if s.strip()]
selected_slugs = list(dict.fromkeys(slug_select + extra_slugs))

if st.sidebar.button("Daten neu laden") and selected_slugs:
    with st.spinner("Lade Daten von Flowzz…"):
        df_new = fetch_selected(selected_slugs)
        st.session_state.df = df_new
        df = df_new

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
st.dataframe(filtered_df, use_container_width=True)

# Download
st.download_button("CSV exportieren", filtered_df.to_csv(index=False), "flowzz_export.csv", "text/csv")
