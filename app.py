import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, ClientOptions
from google.cloud import vision
from google.oauth2 import service_account
import re

st.set_page_config(page_title="Brandstof", layout="centered")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# SESSION INIT
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if "session" not in st.session_state:
    st.session_state.session = None

# -------------------------
# AUTH CLIENT (SAFE)
# -------------------------
def get_auth_client():
    session = st.session_state.session

    if session is None:
        st.error("❌ Geen session (niet ingelogd)")
        return None

    if not hasattr(session, "access_token"):
        st.error("❌ Geen access token")
        return None

    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            headers={
                "Authorization": f"Bearer {session.access_token}"
            }
        )
    )

# -------------------------
# OCR CLIENT
# -------------------------
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
# OCR PARSER
# -------------------------
def parse_bon(text):
    text = text.lower()

    numbers = re.findall(r'\d+[.,]\d+', text)
    numbers = [float(n.replace(",", ".")) for n in numbers]

    liters = None
    prijs = None

    for n in numbers:
        if 10 < n < 100:
            liters = n
        elif 1 < n < 5:
            prijs = n

    if liters and not prijs and numbers:
        prijs = max(numbers) / liters

    return liters, prijs

# -------------------------
# LOGIN
# -------------------------
def login():
    st.title("Login")

    email = st.text_input("Email")
    password = st.text_input("Wachtwoord", type="password")

    if st.button("Login"):
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
            st.error(e)

# -------------------------
# NIEUWE ENTRY
# -------------------------
def nieuwe():

    st.subheader("Nieuwe tankbeurt")

    liters = st.number_input("Liters", value=0.0)
    prijs = st.number_input("Prijs per liter", value=0.0)
    km = st.number_input("KM", value=0.0)

    totaal = liters * prijs

    st.metric("Totaal", f"€ {totaal:.2f}")

    if st.button("Opslaan"):

        auth = get_auth_client()
        if auth is None:
            return

        try:
            res = auth.table("tankbeurten").insert({
                "user_id": st.session_state.user.id,
                "datum": str(datetime.today().date()),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal
            }).execute()

            st.write(res)  # 🔥 debug
            st.success("Opgeslagen")
            st.rerun()

        except Exception as e:
            st.error(f"Insert fout: {e}")

# -------------------------
# DASHBOARD
# -------------------------
def dashboard():

    st.subheader("Dashboard")

    auth = get_auth_client()
    if auth is None:
        return

    try:
        res = auth.table("tankbeurten").select("*").execute()

        st.write(res)  # 🔥 debug

        data = res.data

        if not data:
            st.warning("Geen data gevonden")
            return

        df = pd.DataFrame(data)

        df = df.drop(columns=["id", "user_id"], errors="ignore")

        st.dataframe(df)

    except Exception as e:
        st.error(f"Select fout: {e}")

# -------------------------
# MAIN
# -------------------------
if st.session_state.user is None:
    login()
else:
    tab1, tab2 = st.tabs(["Nieuw", "Dashboard"])

    with tab1:
        nieuwe()

    with tab2:
        dashboard()

    if st.button("Logout"):
        st.session_state.user = None
        st.session_state.session = None
        st.rerun()