import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, ClientOptions
from google.cloud import vision
from google.oauth2 import service_account
import streamlit.components.v1 as components
from streamlit_cookies_manager import EncryptedCookieManager
import re

st.set_page_config(page_title="Brandstof", layout="centered")

# -------------------------
# COOKIES (LOGIN BEWAREN)
# -------------------------
cookies = EncryptedCookieManager(
    prefix="brandstof_app",
    password="super_secret_key"
)

if not cookies.ready():
    st.stop()

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
# AUTO LOGIN (via cookie)
# -------------------------
if st.session_state.session is None:
    token = cookies.get("access_token")

    if token:
        st.session_state.session = type("obj", (), {"access_token": token})
        st.session_state.user = type("obj", (), {"id": "cached_user"})

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
# GPS
# -------------------------
gps = components.html("""
<script>
navigator.geolocation.getCurrentPosition(
    (pos) => {
        const data = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude
        };
        window.parent.postMessage(
            {isStreamlitMessage: true, type: "streamlit:setComponentValue", value: data},
            "*"
        );
    }
);
</script>
""", height=0)

# -------------------------
# TANKSTATIONS
# -------------------------
TANKSTATIONS = [
    "Shell", "BP", "Esso", "Texaco", "Total", "Q8",
    "Tango", "Firezone", "OK", "Gulf", "AVIA",
    "Argos", "Tinq", "Sakko", "Lukoil",
    "Fieten Olie", "Berkman", "De Haan",
    "Tamoil", "Makro", "Sligro", "Anders"
]

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

            cookies["access_token"] = res.session.access_token
            cookies.save()

            st.rerun()

        except Exception as e:
            st.error(e)

# -------------------------
# NIEUWE ENTRY
# -------------------------
def nieuwe():

    st.subheader("Nieuwe tankbeurt")

    with st.form("tank_form", clear_on_submit=True):

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

        submit = st.form_submit_button("Opslaan")

        if submit:

            auth = get_auth_client()
            if auth is None:
                st.stop()

            lat, lon = None, None
            if gps and isinstance(gps, dict):
                lat = gps.get("lat")
                lon = gps.get("lon")

            try:
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

    data = auth.table("tankbeurten").select("*").execute().data

    if not data:
        st.info("Geen data")
        return

    df = pd.DataFrame(data)
    df["datum"] = pd.to_datetime(df["datum"])

    totaal_kosten = df["totaal"].sum()
    totaal_km = df["km"].sum()
    kosten_per_km = totaal_kosten / totaal_km if totaal_km > 0 else 0

    col1, col2 = st.columns(2)
    col1.metric("Totaal €", f"{totaal_kosten:.2f}")
    col2.metric("€/km", f"{kosten_per_km:.3f}")

    df = df.sort_values("datum")

    st.line_chart(df.set_index("datum")["totaal"])

    df_display = df.drop(columns=["id", "user_id", "latitude", "longitude"], errors="ignore")
    st.dataframe(df_display, use_container_width=True)

    map_df = df.dropna(subset=["latitude", "longitude"])
    if not map_df.empty:
        st.map(map_df.rename(columns={"latitude": "lat", "longitude": "lon"}))

# -------------------------
# MAIN
# -------------------------
if st.session_state.session is None:
    login()
else:
    tab1, tab2 = st.tabs(["Nieuw", "Dashboard"])

    with tab1:
        nieuwe()

    with tab2:
        dashboard()

    if st.button("Logout"):
        cookies["access_token"] = ""
        cookies.save()

        st.session_state.user = None
        st.session_state.session = None
        st.rerun()