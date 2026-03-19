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
# GOOGLE OCR INIT
# ------------------------
vision_client = None

if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in st.secrets:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"].encode())
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name

        vision_client = vision.ImageAnnotatorClient()
    except:
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
# OCR SCAN
# ------------------------
def scan_bon(file):
    if not vision_client:
        return ""

    content = file.read()

    image = vision.Image(content=content)
    response = vision_client.text_detection(image=image)

    if response.text_annotations:
        return response.text_annotations[0].description

    return ""

# ------------------------
# PARSING
# ------------------------
def parse_bon(text):
    liters = None
    prijs = None
    brandstof = None

    # liters
    match_liters = re.search(r"(\d+[.,]\d+)\s*(L|liter)", text, re.IGNORECASE)
    if match_liters:
        liters = float(match_liters.group(1).replace(",", "."))

    # prijs
    match_prijs = re.search(r"€?\s*(\d+[.,]\d+)", text)
    if match_prijs:
        prijs = float(match_prijs.group(1).replace(",", "."))

    # brandstof
    if "diesel" in text.lower():
        brandstof = "diesel"
    elif "95" in text:
        brandstof = "euro 95"

    return liters, prijs, brandstof

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
# NAV
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

    # OCR upload
    uploaded_file = st.file_uploader("Upload bon", type=["jpg", "png"])

    liters = 0.0
    prijs = 0.0
    brandstof = ""

    if uploaded_file:
        text = scan_bon(uploaded_file)
        st.text_area("Herkende tekst", text, height=150)

        liters, prijs, brandstof = parse_bon(text)

    datum = st.date_input("Datum", value=date.today())
    liters = st.number_input("Liters", value=liters)
    prijs = st.number_input("Prijs", value=prijs)
    km = st.number_input("KM", value=0.0)

    brandstof = st.selectbox(
        "Brandstof",
        ["", "euro 95", "diesel", "euro 98", "elektrisch"],
        index=0 if brandstof == "" else ["", "euro 95", "diesel", "euro 98", "elektrisch"].index(brandstof)
    )

    totaal = liters * prijs
    kosten_km = totaal / km if km > 0 else 0

    st.write(f"Totaal: €{totaal:.2f}")
    st.write(f"Kosten per km: €{kosten_km:.2f}")

    if st.button("Opslaan"):
        apply_session()

        supabase.table("tankbeurten").insert({
            "user_id": st.session_state.user_id,
            "datum": str(datum),
            "liters": liters,
            "prijs": prijs,
            "km": km,
            "totaal": totaal,
            "brandstof": brandstof
        }).execute()

        st.success("Opgeslagen")

# ------------------------
# DASHBOARD
# ------------------------
def dashboard():
    st.subheader("Dashboard")

    apply_session()

    res = supabase.table("tankbeurten").select("*").execute()
    data = res.data

    if not data:
        st.warning("Geen data")
        return

    df = pd.DataFrame(data)
    df_display = df.drop(columns=["id", "user_id"], errors="ignore")

    st.dataframe(df_display)

    st.write("Totale kosten:", df["totaal"].sum())

    # DELETE
    ids = df["id"].tolist()
    selected = st.selectbox("Verwijder", ids)

    if st.button("Delete"):
        apply_session()
        supabase.table("tankbeurten").delete().eq("id", selected).execute()
        st.rerun()

# ------------------------
# MAIN
# ------------------------
if st.session_state.session is None:
    login()
else:
    st.success(f"Ingelogd als: {st.session_state.user_id}")

    navigation()

    if st.session_state.page == "nieuw":
        nieuwe_tankbeurt()

    elif st.session_state.page == "dashboard":
        dashboard()