import streamlit as st
import pandas as pd
from datetime import date
import re
import os
import tempfile

from supabase import create_client
from google.cloud import vision

# ------------------------
# CONFIG
# ------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------
# GOOGLE OCR (FIXED)
# ------------------------
vision_client = None

if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in st.secrets:
    try:
        creds_json = st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(creds_json.encode("utf-8"))
            temp_path = f.name

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path

        vision_client = vision.ImageAnnotatorClient()

    except Exception as e:
        st.error(f"OCR init fout: {e}")
        vision_client = None

# ------------------------
# SESSION
# ------------------------
if "session" not in st.session_state:
    st.session_state.session = None

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "page" not in st.session_state:
    st.session_state.page = "login"

# ------------------------
# AUTH FIX
# ------------------------
def apply_session():
    if st.session_state.session:
        supabase.auth.set_session(
            st.session_state.session.session.access_token,
            st.session_state.session.session.refresh_token
        )

# ------------------------
# OCR FUNCTION
# ------------------------
def scan_bon(file):
    if not vision_client:
        st.warning("OCR niet actief")
        return ""

    content = file.read()

    image = vision.Image(content=content)
    response = vision_client.text_detection(image=image)

    if response.error.message:
        st.error(response.error.message)
        return ""

    if response.text_annotations:
        return response.text_annotations[0].description

    return ""

# ------------------------
# PARSING
# ------------------------
def parse_bon(text):
    text_lower = text.lower()

    liters = None
    prijs = None
    brandstof = None
    station = None

    # liters
    match_liters = re.search(r"(\d+[.,]\d+)\s*(l|liter)", text_lower)
    if match_liters:
        liters = float(match_liters.group(1).replace(",", "."))

    # prijs
    match_prijs = re.search(r"€\s*(\d+[.,]\d+)", text_lower)
    if match_prijs:
        prijs = float(match_prijs.group(1).replace(",", "."))

    # brandstof
    if "diesel" in text_lower:
        brandstof = "diesel"
    elif "95" in text_lower:
        brandstof = "euro 95"
    elif "98" in text_lower:
        brandstof = "euro 98"

    # stations
    stations = ["shell", "bp", "esso", "texaco", "tango", "avia", "berkman", "pin&go"]

    for s in stations:
        if s in text_lower:
            station = s.capitalize()

    return liters, prijs, brandstof, station

# ------------------------
# LOGIN
# ------------------------
def login():
    st.title("Brandstof App")

    email = st.text_input("Email")
    password = st.text_input("Wachtwoord", type="password")

    if st.button("Login"):
        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            st.session_state.session = res
            st.session_state.user_id = res.user.id
            st.session_state.page = "home"

            st.rerun()

        except:
            st.error("Login mislukt")

# ------------------------
# NAVIGATIE
# ------------------------
def navigation():
    col1, col2, col3 = st.columns(3)

    if col1.button("Nieuwe tankbeurt"):
        st.session_state.page = "nieuw"

    if col2.button("Dashboard"):
        st.session_state.page = "dashboard"

    if col3.button("Logout"):
        st.session_state.session = None
        st.rerun()

# ------------------------
# NIEUWE ENTRY
# ------------------------
def nieuwe_tankbeurt():
    st.subheader("Nieuwe tankbeurt")

    st.write("OCR status:", "Actief" if vision_client else "Niet actief")

    uploaded_file = st.file_uploader("Upload bon", type=["jpg", "png"])

    liters = 0.0
    prijs = 0.0
    brandstof = ""
    station = ""

    if uploaded_file:
        text = scan_bon(uploaded_file)

        st.text_area("Herkende tekst", text, height=150)

        l, p, b, s = parse_bon(text)

        if l: liters = l
        if p: prijs = p
        if b: brandstof = b.lower().strip()
        if s: station = s

    datum = st.date_input("Datum", value=date.today())
    liters = st.number_input("Liters", value=float(liters))
    prijs = st.number_input("Prijs (€)", value=float(prijs))
    km = st.number_input("KM", value=0.0)

    opties = ["", "euro 95", "diesel", "euro 98"]

    if brandstof in opties:
        index = opties.index(brandstof)
    else:
        index = 0

    brandstof = st.selectbox("Brandstof", opties, index=index)
    station = st.text_input("Tankstation", value=station)

    lat = st.number_input("Latitude", value=0.0)
    lon = st.number_input("Longitude", value=0.0)
    adres = st.text_input("Adres")

    if lat != 0 and lon != 0:
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))

    totaal = liters * prijs
    kosten_km = totaal / km if km > 0 else 0

    st.write(f"Totaal: €{totaal:.2f}")
    st.write(f"Kosten per km: €{kosten_km:.2f}")

    if st.button("Opslaan"):
        try:
            apply_session()

            supabase.table("tankbeurten").insert({
                "user_id": st.session_state.user_id,
                "datum": str(datum),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal,
                "brandstof": brandstof,
                "station": station,
                "latitude": lat if lat != 0 else None,
                "longitude": lon if lon != 0 else None,
                "adres": adres
            }).execute()

            st.success("Opgeslagen")

        except Exception as e:
            st.error(f"Opslaan mislukt: {e}")

# ------------------------
# DASHBOARD
# ------------------------
def dashboard():
    st.subheader("Dashboard")

    try:
        apply_session()

        res = supabase.table("tankbeurten").select("*").execute()
        data = res.data

        if not data:
            st.warning("Geen data")
            return

        df = pd.DataFrame(data)

        df_display = df.drop(columns=["id", "user_id"], errors="ignore")
        st.dataframe(df_display)

        # kaart
        df_map = df.dropna(subset=["latitude", "longitude"])
        if not df_map.empty:
            st.map(df_map.rename(columns={"latitude": "lat", "longitude": "lon"}))

        st.write("Totale kosten:", df["totaal"].sum())

        ids = df["id"].tolist()
        selected = st.selectbox("Verwijder record", ids)

        if st.button("Verwijder"):
            apply_session()
            supabase.table("tankbeurten").delete().eq("id", selected).execute()
            st.rerun()

    except Exception as e:
        st.error(f"Fout bij ophalen data: {e}")

# ------------------------
# MAIN
# ------------------------
if st.session_state.session is None:
    login()
else:
    st.success("Ingelogd")

    navigation()

    if st.session_state.page == "nieuw":
        nieuwe_tankbeurt()

    elif st.session_state.page == "dashboard":
        dashboard()

    else:
        st.title("Welkom")