import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client
from google.cloud import vision
from google.oauth2 import service_account
import re

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="Brandstof App", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# OCR SETUP (FIXED)
# -----------------------------
vision_client = None

try:
    credentials = service_account.Credentials.from_service_account_info({
        "type": "service_account",
        "project_id": st.secrets["GOOGLE_PROJECT_ID"],
        "private_key": st.secrets["GOOGLE_PRIVATE_KEY"].replace("\\n", "\n"),
        "client_email": st.secrets["GOOGLE_CLIENT_EMAIL"],
        "token_uri": "https://oauth2.googleapis.com/token",
    })

    vision_client = vision.ImageAnnotatorClient(credentials=credentials)

except Exception as e:
    st.warning("OCR niet actief")

# -----------------------------
# HELPER: OCR PARSING
# -----------------------------
def parse_bon(text):
    liters = None
    prijs = None

    # liters
    match = re.search(r'(\d+[.,]\d+)\s*L', text)
    if match:
        liters = float(match.group(1).replace(",", "."))

    # prijs
    match = re.search(r'€\s?(\d+[.,]\d+)', text)
    if match:
        prijs = float(match.group(1).replace(",", "."))

    return liters, prijs

# -----------------------------
# LOGIN
# -----------------------------
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
            st.session_state["user"] = res.user
            st.rerun()
        except:
            st.error("Login mislukt")

# -----------------------------
# LOGOUT
# -----------------------------
def logout():
    st.session_state.clear()
    st.rerun()

# -----------------------------
# NIEUWE TANKBEURT
# -----------------------------
def nieuwe_tankbeurt():

    st.header("Nieuwe tankbeurt")

    uploaded = st.file_uploader("Upload bon", type=["jpg", "png", "jpeg"])

    liters = st.number_input("Liters", value=0.0)
    prijs = st.number_input("Prijs per liter", value=0.0)
    km = st.number_input("Kilometerstand", value=0.0)

    brandstof = st.selectbox("Brandstof", ["", "euro 95", "diesel", "euro 98", "elektrisch"])

    station = st.selectbox("Tankstation", [
        "", "Shell", "BP", "Total", "Texaco", "Esso",
        "AVIA", "Berkman", "Pin&Go"
    ])

    lat = None
    lon = None
    adres = None

    # OCR
    if uploaded and vision_client:
        image = vision.Image(content=uploaded.read())
        response = vision_client.text_detection(image=image)
        text = response.text_annotations[0].description if response.text_annotations else ""

        l, p = parse_bon(text)

        if l:
            liters = l
        if p:
            prijs = p

        st.success("OCR toegepast")

    if st.button("Opslaan"):
        totaal = liters * prijs
        cost_per_km = totaal / km if km > 0 else 0

        try:
            supabase.table("tankbeurten").insert({
                "user_id": st.session_state["user"].id,
                "datum": str(datetime.today().date()),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal,
                "brandstof": brandstof,
                "station": station,
                "latitude": lat,
                "longitude": lon,
                "adres": adres
            }).execute()

            st.success("Opgeslagen!")
            st.rerun()

        except Exception as e:
            st.error("Opslaan mislukt")

# -----------------------------
# DASHBOARD
# -----------------------------
def dashboard():

    st.header("Dashboard")

    user_id = st.session_state["user"].id

    try:
        data = supabase.table("tankbeurten") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        rows = data.data

        if not rows:
            st.warning("Geen data")
            return

        df = pd.DataFrame(rows)

        # kosten per km
        df["kosten_per_km"] = df["totaal"] / df["km"]

        # nette tabel
        st.dataframe(df[[
            "datum", "liters", "prijs", "km",
            "totaal", "kosten_per_km", "brandstof", "station"
        ]])

        st.metric("Totale kosten", round(df["totaal"].sum(), 2))

        # verwijderen
        st.subheader("Verwijderen")

        delete_id = st.selectbox(
            "Selecteer record",
            df["id"]
        )

        if st.button("Verwijder"):
            supabase.table("tankbeurten").delete().eq("id", delete_id).execute()
            st.success("Verwijderd")
            st.rerun()

        # kaart
        if "latitude" in df and df["latitude"].notna().any():
            st.subheader("Kaart")
            st.map(df.rename(columns={
                "latitude": "lat",
                "longitude": "lon"
            }))

    except:
        st.error("Fout bij ophalen data")

# -----------------------------
# MAIN
# -----------------------------
if "user" not in st.session_state:
    login()
else:
    st.success(f"Ingelogd als: {st.session_state['user'].email}")

    col1, col2, col3 = st.columns(3)

    if col1.button("Nieuwe tankbeurt"):
        st.session_state["page"] = "new"

    if col2.button("Dashboard"):
        st.session_state["page"] = "dashboard"

    if col3.button("Logout"):
        logout()

    if "page" not in st.session_state:
        st.session_state["page"] = "dashboard"

    if st.session_state["page"] == "new":
        nieuwe_tankbeurt()
    else:
        dashboard()