import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client
from google.cloud import vision
from google.oauth2 import service_account
import re

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title="Brandstof", layout="centered")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# basis client (zonder auth)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# SESSION
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if "session" not in st.session_state:
    st.session_state.session = None

# -------------------------
# AUTH CLIENT (BELANGRIJK)
# -------------------------
def get_auth_client():
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options={
            "headers": {
                "Authorization": f"Bearer {st.session_state.session.access_token}"
            }
        }
    )

# -------------------------
# OCR CLIENT
# -------------------------
@st.cache_resource
def get_vision_client():
    try:
        credentials = service_account.Credentials.from_service_account_info({
            "type": "service_account",
            "project_id": st.secrets["GOOGLE_PROJECT_ID"],
            "private_key": st.secrets["GOOGLE_PRIVATE_KEY"].replace("\\n", "\n"),
            "client_email": st.secrets["GOOGLE_CLIENT_EMAIL"],
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        return vision.ImageAnnotatorClient(credentials=credentials)
    except:
        return None

vision_client = get_vision_client()

# -------------------------
# CACHE DATA
# -------------------------
@st.cache_data(ttl=10)
def load_data():
    auth_supabase = get_auth_client()
    return auth_supabase.table("tankbeurten") \
        .select("id, datum, liters, prijs, km, totaal, brandstof, station") \
        .order("datum", desc=True) \
        .execute().data

# -------------------------
# PARSING
# -------------------------
def parse_bon(text):
    liters = None
    prijs = None

    match = re.search(r'(\d+[.,]\d+)\s*L', text)
    if match:
        liters = float(match.group(1).replace(",", "."))

    match = re.search(r'€\s?(\d+[.,]\d+)', text)
    if match:
        prijs = float(match.group(1).replace(",", "."))

    return liters, prijs

# -------------------------
# LOGIN
# -------------------------
def login():
    st.title("Brandstof App")

    email = st.text_input("Email")
    password = st.text_input("Wachtwoord", type="password")

    if st.button("Login", use_container_width=True):
        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            st.session_state.user = res.user
            st.session_state.session = res.session

            st.success("Ingelogd")
            st.rerun()

        except Exception as e:
            st.error(f"Login fout: {e}")

# -------------------------
# NIEUWE TANKBEURT
# -------------------------
def nieuwe_tankbeurt():

    st.subheader("Nieuwe tankbeurt")

    uploaded = st.file_uploader("Scan bon", type=["jpg", "png", "jpeg"])

    liters = 0.0
    prijs = 0.0

    if uploaded and vision_client:
        try:
            image = vision.Image(content=uploaded.read())
            response = vision_client.text_detection(image=image)

            text = response.text_annotations[0].description if response.text_annotations else ""
            l, p = parse_bon(text)

            if l: liters = l
            if p: prijs = p

            st.success("OCR toegepast")

        except:
            st.warning("OCR mislukt")

    liters = st.number_input("Liters", value=float(liters))
    prijs = st.number_input("Prijs per liter", value=float(prijs))
    km = st.number_input("KM", value=0.0)

    brandstof = st.selectbox("Brandstof", ["euro 95", "diesel", "euro 98"])
    station = st.selectbox("Tankstation", [
        "Shell", "BP", "Esso", "Texaco", "Total",
        "Tango", "AVIA", "Berkman", "Pin&Go"
    ])

    totaal = liters * prijs
    kosten_km = totaal / km if km > 0 else 0

    st.metric("Totaal", f"€ {totaal:.2f}")
    st.metric("€/km", f"€ {kosten_km:.2f}")

    if st.button("Opslaan", use_container_width=True):
        try:
            auth_supabase = get_auth_client()

            auth_supabase.table("tankbeurten").insert({
                "user_id": st.session_state.user.id,
                "datum": str(datetime.today().date()),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal,
                "brandstof": brandstof,
                "station": station
            }).execute()

            st.cache_data.clear()
            st.success("Opgeslagen")
            st.rerun()

        except Exception as e:
            st.error(f"Opslaan mislukt: {e}")

# -------------------------
# DASHBOARD
# -------------------------
def dashboard():

    st.subheader("Dashboard")

    data = load_data()

    if not data:
        st.info("Nog geen data")
        return

    df = pd.DataFrame(data)
    df["kosten_per_km"] = df["totaal"] / df["km"]

    for _, row in df.iterrows():
        st.markdown(f"""
        **{row['datum']}**  
        {row['station']} - {row['brandstof']}  
        {row['liters']}L | €{row['totaal']:.2f}  
        €{row['kosten_per_km']:.2f}/km
        """)
        st.divider()

    st.metric("Totale kosten", f"€ {df['totaal'].sum():.2f}")

    with st.expander("Verwijderen"):
        delete_id = st.selectbox("Selecteer", df["id"])

        if st.button("Verwijder"):
            auth_supabase = get_auth_client()

            auth_supabase.table("tankbeurten") \
                .delete() \
                .eq("id", delete_id) \
                .execute()

            st.cache_data.clear()
            st.rerun()

# -------------------------
# MAIN
# -------------------------
if st.session_state.user is None:
    login()
else:
    st.title("Brandstof")

    tab1, tab2 = st.tabs(["Nieuw", "Overzicht"])

    with tab1:
        nieuwe_tankbeurt()

    with tab2:
        dashboard()

    if st.button("Logout"):
        st.session_state.user = None
        st.session_state.session = None
        st.rerun()