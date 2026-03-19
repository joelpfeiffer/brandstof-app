import streamlit as st
import pandas as pd
import re
import requests
from supabase import create_client
from streamlit_cookies_manager import EncryptedCookieManager
from google.cloud import vision
from streamlit_geolocation import streamlit_geolocation
import os

# ------------------------
# CONFIG
# ------------------------
st.set_page_config(page_title="Brandstof", layout="centered")

# PWA
st.markdown('<link rel="manifest" href="/.streamlit/manifest.json">', unsafe_allow_html=True)

# ------------------------
# SUPABASE
# ------------------------
url = "https://tgwzdxwtshgviyxwalmo.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRnd3pkeHd0c2hndml5eHdhbG1vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5NDE2ODAsImV4cCI6MjA4OTUxNzY4MH0.41lUYaL9z0TYbN8xJu9ZIfjg23dVzJvInpDvVdeFOLE"
supabase = create_client(url, key)

# ------------------------
# COOKIES
# ------------------------
cookies = EncryptedCookieManager(prefix="app", password="123")

if not cookies.ready():
    st.stop()

# ------------------------
# SESSION
# ------------------------
if "user" not in st.session_state:
    st.session_state.user = None
    st.session_state.user_id = None

# ------------------------
# LOGIN HERSTEL
# ------------------------
if not st.session_state.user:
    access = cookies.get("access_token")
    refresh = cookies.get("refresh_token")

    if access and refresh:
        try:
            supabase.auth.set_session(access, refresh)
            user = supabase.auth.get_user()
            st.session_state.user = user.user
            st.session_state.user_id = user.user.id
        except:
            pass

# ------------------------
# LOGIN
# ------------------------
if not st.session_state.user:

    st.title("Brandstof App")

    email = st.text_input("Email")
    password = st.text_input("Wachtwoord", type="password")

    if st.button("Inloggen", use_container_width=True):
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        st.session_state.user = res.user
        st.session_state.user_id = res.user.id

        cookies["access_token"] = res.session.access_token
        cookies["refresh_token"] = res.session.refresh_token
        cookies.save()

        st.rerun()

    st.stop()

# ------------------------
# HEADER
# ------------------------
st.title("Brandstof App")
st.caption(f"Ingelogd als {st.session_state.user.email}")

if st.button("Uitloggen", use_container_width=True):
    st.session_state.user = None
    cookies.clear()
    st.rerun()

st.divider()

# ------------------------
# MENU
# ------------------------
page = st.segmented_control("Navigatie", ["Nieuwe invoer", "Dashboard"])

# ------------------------
# OCR
# ------------------------
try:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "brandstof-app-490719-1da7dbf30c40.json"
    vision_client = vision.ImageAnnotatorClient()
except:
    vision_client = None

def scan_bon(file):
    if not vision_client:
        return ""
    image = vision.Image(content=file.getvalue())
    response = vision_client.text_detection(image=image)
    if response.text_annotations:
        return response.text_annotations[0].description
    return ""

# ------------------------
# STATION LIJST
# ------------------------
stations = [
    "shell","bp","esso","texaco","total","totalenergies",
    "q8","avia","tango","tinq","firezone","tamoil",
    "gulf","argos","haan","fieten","sakko",
    "fuel up","kreuze","ok","snel tank",
    "berkman","pin&go","pingo","pin go"
]

def detect_station(text):
    for s in stations:
        if s in text:
            return s.title()
    return ""

# ------------------------
# PARSING
# ------------------------
def parse_text(text):
    text = text.lower().replace(",", ".")
    nums = [float(n) for n in re.findall(r"\d+\.\d+", text)]

    liters = prijs = totaal = None

    m = re.search(r"(95|98|diesel)[^\d]*(\d+\.\d+)", text)
    if m:
        liters = float(m.group(2))

    prijzen = [n for n in nums if 1 < n < 3]
    if prijzen:
        prijs = prijzen[0]

    totals = [n for n in nums if 10 < n < 200]
    if totals:
        totaal = max(totals)

    if not liters and prijs and totaal:
        liters = totaal / prijs

    return liters, prijs, totaal

# ------------------------
# ADRES
# ------------------------
def get_address(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        headers = {"User-Agent": "brandstof-app"}
        return requests.get(url, headers=headers).json().get("display_name", "")
    except:
        return ""

# ------------------------
# INPUT
# ------------------------
if page == "Nieuwe invoer":

    st.subheader("Nieuwe tankbeurt")

    uploaded = st.file_uploader("Upload bon", type=["jpg","png","jpeg"])

    ocr_liters = ocr_prijs = None
    station_auto = ""

    if uploaded:
        text = scan_bon(uploaded)
        st.expander("Herkende tekst").write(text)

        ocr_liters, ocr_prijs, _ = parse_text(text)
        station_auto = detect_station(text.lower())

    loc = streamlit_geolocation()
    lat = lon = None

    if loc:
        lat = loc["latitude"]
        lon = loc["longitude"]

    with st.form("form"):
        datum = st.date_input("Datum")
        liters = st.number_input("Liters", value=ocr_liters or 0.0)
        prijs = st.number_input("Prijs (€)", value=ocr_prijs or 0.0)
        km = st.number_input("Kilometers", min_value=0.0)
        station = st.text_input("Tankstation", value=station_auto)

        submitted = st.form_submit_button("Opslaan")

        if submitted:
            totaal = liters * prijs
            adres = get_address(lat, lon) if lat else ""

            supabase.table("tankbeurten").insert({
                "user_id": st.session_state.user_id,
                "datum": str(datum),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal,
                "station": station,
                "latitude": lat,
                "longitude": lon,
                "adres": adres
            }).execute()

            st.success("Tankbeurt opgeslagen")

# ------------------------
# DASHBOARD
# ------------------------
if page == "Dashboard":

    data = supabase.table("tankbeurten") \
        .select("*") \
        .eq("user_id", str(st.session_state.user_id)) \
        .execute().data

    if not data:
        st.info("Nog geen gegevens beschikbaar")
        st.stop()

    df = pd.DataFrame(data)
    df["datum"] = pd.to_datetime(df["datum"])

    # KPI
    col1, col2, col3 = st.columns(3)

    kosten = df["totaal"].sum()
    km = df["km"].sum()
    liters = df["liters"].sum()

    col1.metric("Totale kosten", f"€{kosten:.2f}")
    col2.metric("Km per liter", f"{km/liters:.2f}")
    col3.metric("Kosten per km", f"€{kosten/km:.2f}")

    st.divider()

    # Grafieken
    st.subheader("Kosten over tijd")
    st.line_chart(df.set_index("datum")["totaal"])

    st.subheader("Kosten per maand")
    df["maand"] = df["datum"].dt.to_period("M").astype(str)
    st.bar_chart(df.groupby("maand")["totaal"].sum())

    # Kaart
    map_df = df.dropna(subset=["latitude","longitude"])
    if not map_df.empty:
        st.subheader("Locaties")
        st.map(map_df.rename(columns={"latitude":"lat","longitude":"lon"}))

    st.divider()

    # Tabel
    st.subheader("Overzicht")

    cols = [c for c in df.columns if c not in ["id", "user_id"]]
    st.dataframe(df[cols], use_container_width=True)

    # Delete
    st.subheader("Verwijderen")

    delete_id = st.selectbox("Selecteer record", df["id"])
    confirm = st.checkbox("Bevestig verwijderen")

    if st.button("Verwijder record") and confirm:
        supabase.table("tankbeurten").delete().eq("id", delete_id).execute()
        st.success("Record verwijderd")
        st.rerun()
