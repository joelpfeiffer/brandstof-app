import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, ClientOptions
from google.cloud import vision
from google.oauth2 import service_account
import re

# -------------------------
# UI (MOBILE FIX)
# -------------------------
st.set_page_config(page_title="Brandstof", layout="centered")

st.markdown("""
<style>
button {
    height: 60px !important;
    font-size: 18px !important;
}
</style>
""", unsafe_allow_html=True)

# -------------------------
# CONFIG
# -------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# SESSION
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if "session" not in st.session_state:
    st.session_state.session = None

# -------------------------
# AUTH CLIENT (RLS FIX)
# -------------------------
def get_auth_client():
    if st.session_state.session is None:
        return None

    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            headers={
                "Authorization": f"Bearer {st.session_state.session.access_token}"
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
    except Exception as e:
        st.warning(f"OCR niet actief: {e}")
        return None

vision_client = get_vision_client()

# -------------------------
# OCR PARSER (VERBETERD)
# -------------------------
def parse_bon(text):
    liters = None
    prijs = None

    text = text.lower()

    liter_patterns = [
        r'(\d+[.,]\d+)\s*l',
        r'l\s*(\d+[.,]\d+)',
        r'volume\s*(\d+[.,]\d+)',
    ]

    for pattern in liter_patterns:
        match = re.search(pattern, text)
        if match:
            liters = float(match.group(1).replace(",", "."))
            break

    prijs_patterns = [
        r'€\s?(\d+[.,]\d+)',
        r'(\d+[.,]\d+)\s*euro',
    ]

    for pattern in prijs_patterns:
        match = re.search(pattern, text)
        if match:
            prijs = float(match.group(1).replace(",", "."))
            break

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

    if st.session_state.session is None:
        st.error("Niet ingelogd")
        return

    st.subheader("Nieuwe tankbeurt")

    uploaded = st.file_uploader("Scan bon", type=["jpg", "png", "jpeg"])

    liters = 0.0
    prijs = 0.0

    if uploaded and vision_client:
        try:
            image = vision.Image(content=uploaded.read())
            response = vision_client.text_detection(image=image)

            text = response.text_annotations[0].description if response.text_annotations else ""

            # DEBUG OCR TEXT
            st.text_area("OCR tekst", text, height=150)

            l, p = parse_bon(text)

            if l: liters = l
            if p: prijs = p

            st.success("OCR toegepast")

        except Exception as e:
            st.warning(f"OCR mislukt: {e}")

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

            if auth_supabase is None:
                st.error("Geen sessie")
                return

            res = auth_supabase.table("tankbeurten").insert({
                "user_id": st.session_state.user.id,
                "datum": str(datetime.today().date()),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal,
                "brandstof": brandstof,
                "station": station
            }).execute()

            # DEBUG RESPONSE
            st.write(res)

            st.success("Opgeslagen")
            st.rerun()

        except Exception as e:
            st.error(f"Opslaan mislukt: {e}")

# -------------------------
# DASHBOARD
# -------------------------
def dashboard():

    if st.session_state.session is None:
        st.error("Niet ingelogd")
        return

    st.subheader("Overzicht")

    try:
        auth_supabase = get_auth_client()

        data = auth_supabase.table("tankbeurten") \
            .select("*") \
            .order("datum", desc=True) \
            .execute().data

        if not data:
            st.info("Nog geen tankbeurten")
            return

        df = pd.DataFrame(data)
        df["kosten_per_km"] = df["totaal"] / df["km"]

        # STATS
        col1, col2 = st.columns(2)
        col1.metric("Totaal", f"€ {df['totaal'].sum():.2f}")
        col2.metric("Gem €/km", f"€ {df['kosten_per_km'].mean():.2f}")

        st.divider()

        # LIST
        for _, row in df.iterrows():
            with st.container():
                st.markdown(f"""
                **{row['datum']}**  
                {row['station']} • {row['brandstof']}
                """)

                col1, col2, col3 = st.columns(3)
                col1.write(f"{row['liters']} L")
                col2.write(f"€ {row['totaal']:.2f}")
                col3.write(f"€ {row['kosten_per_km']:.2f}/km")

                st.divider()

    except Exception as e:
        st.error(f"Dashboard fout: {e}")

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