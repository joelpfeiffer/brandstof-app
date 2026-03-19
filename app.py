import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, ClientOptions
from google.cloud import vision
from google.oauth2 import service_account
import re

st.set_page_config(page_title="Brandstof", layout="centered")

# -------------------------
# CONFIG
# -------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# TANKSTATIONS
# -------------------------
TANKSTATIONS = [
    "Shell", "BP", "Esso", "Texaco", "Total", "Q8",
    "Tango", "Firezone", "OK", "Gulf", "AVIA",
    "Argos", "Tinq", "Sakko", "Lukoil",
    "Fieten Olie", "Berkman", "De Haan", "Tamoil",
    "Makro", "Sligro", "Anders"
]

# -------------------------
# SESSION
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "session" not in st.session_state:
    st.session_state.session = None

# -------------------------
# AUTH CLIENT
# -------------------------
def get_auth_client():
    session = st.session_state.session
    if session is None:
        st.error("Niet ingelogd")
        return None

    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            headers={"Authorization": f"Bearer {session.access_token}"}
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
# OCR PARSE
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

    if liters and prijs and prijs > 10:
        prijs = prijs / liters

    return liters, prijs

# -------------------------
# GPS (simple)
# -------------------------
st.components.v1.html("""
<script>
navigator.geolocation.getCurrentPosition(
    (pos) => {
        const coords = pos.coords.latitude + "," + pos.coords.longitude;
        window.parent.postMessage({type: "streamlit:setComponentValue", value: coords}, "*");
    }
);
</script>
""", height=0)

gps = st.session_state.get("gps")

# -------------------------
# LOGIN
# -------------------------
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
            st.session_state.user = res.user
            st.session_state.session = res.session
            st.rerun()
        except Exception as e:
            st.error(e)

# -------------------------
# NIEUWE TANKBEURT
# -------------------------
def nieuwe():

    st.subheader("Nieuwe tankbeurt")

    uploaded = st.file_uploader("Upload bon", type=["jpg", "png", "jpeg"])

    liters = 0.0
    prijs = 0.0

    if uploaded and vision_client:
        image = vision.Image(content=uploaded.read())
        response = vision_client.text_detection(image=image)

        text = response.text_annotations[0].description if response.text_annotations else ""
        st.text_area("OCR tekst", text, height=120)

        l, p = parse_bon(text)
        if l:
            liters = l
        if p:
            prijs = p

    liters = st.number_input("Liters", value=liters)
    prijs = st.number_input("Prijs per liter", value=prijs)
    km = st.number_input("KM", value=0.0)

    brandstof = st.selectbox("Brandstof", ["euro 95", "diesel", "euro 98"])

    station = st.selectbox("Tankstation", TANKSTATIONS)
    if station == "Anders":
        station = st.text_input("Naam tankstation")

    totaal = liters * prijs
    st.metric("Totaal prijs", f"€ {totaal:.2f}")

    if st.button("Opslaan"):

        auth = get_auth_client()
        if auth is None:
            return

        try:
            lat, lon = None, None
            if gps:
                lat, lon = gps.split(",")

            auth.table("tankbeurten").insert({
                "user_id": st.session_state.user.id,
                "datum": str(datetime.today().date()),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal,
                "brandstof": brandstof,
                "station": station,
                "latitude": lat,
                "longitude": lon
            }).execute()

            st.success("Opgeslagen")
            st.rerun()

        except Exception as e:
            st.error(f"Opslaan fout: {e}")

# -------------------------
# DASHBOARD
# -------------------------
def dashboard():

    st.subheader("Dashboard")

    auth = get_auth_client()
    if auth is None:
        return

    try:
        data = auth.table("tankbeurten").select("*").execute().data

        if not data:
            st.info("Geen data")
            return

        df = pd.DataFrame(data)

        df["datum"] = pd.to_datetime(df["datum"])

        totaal_kosten = df["totaal"].sum()
        totaal_km = df["km"].sum()
        totaal_liters = df["liters"].sum()

        kosten_per_km = totaal_kosten / totaal_km if totaal_km > 0 else 0
        gem_prijs = df["prijs"].mean()

        col1, col2 = st.columns(2)
        col1.metric("Totaal €", f"{totaal_kosten:.2f}")
        col2.metric("€/km", f"{kosten_per_km:.3f}")

        col1, col2 = st.columns(2)
        col1.metric("Gem €/L", f"{gem_prijs:.2f}")
        col2.metric("Beurten", len(df))

        df = df.sort_values("datum")

        st.subheader("Kosten")
        st.line_chart(df.set_index("datum")["totaal"])

        st.subheader("Liters")
        st.line_chart(df.set_index("datum")["liters"])

        st.subheader("Overzicht")

        df_display = df.drop(columns=["id", "user_id", "latitude", "longitude"], errors="ignore")

        st.dataframe(df_display, use_container_width=True)

        st.subheader("Kaart")

        map_df = df.dropna(subset=["latitude", "longitude"])
        if not map_df.empty:
            st.map(map_df.rename(columns={"latitude": "lat", "longitude": "lon"}))

    except Exception as e:
        st.error(f"Dashboard fout: {e}")

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