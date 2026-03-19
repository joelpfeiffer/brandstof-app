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
# SESSION
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if "session" not in st.session_state:
    st.session_state.session = None

if "reset" not in st.session_state:
    st.session_state.reset = False

# -------------------------
# AUTH CLIENT
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
    except:
        return None

vision_client = get_vision_client()

# -------------------------
# OCR PARSER (FIXED)
# -------------------------
def parse_bon(text):
    text = text.lower()

    numbers = re.findall(r'\d+[.,]\d+', text)
    numbers = [float(n.replace(",", ".")) for n in numbers]

    liters = None
    prijs_per_liter = None
    totaal = None

    for n in numbers:
        if 10 < n < 100:
            liters = n
        elif 1 < n < 5:
            prijs_per_liter = n

    if numbers:
        totaal = max(numbers)

    if liters and totaal and not prijs_per_liter:
        prijs_per_liter = totaal / liters

    return liters, prijs_per_liter

# -------------------------
# GPS
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
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        st.session_state.user = res.user
        st.session_state.session = res.session
        st.rerun()

# -------------------------
# NIEUWE ENTRY
# -------------------------
def nieuwe():

    st.subheader("Nieuwe tankbeurt")

    liters = 0.0
    prijs = 0.0

    uploaded = st.file_uploader("Scan bon")

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

    liters = st.number_input("Liters", value=0.0 if st.session_state.reset else liters)
    prijs = st.number_input("Prijs per liter", value=0.0 if st.session_state.reset else prijs)
    km = st.number_input("KM", value=0.0)

    brandstof = st.selectbox("Brandstof", ["euro 95", "diesel", "euro 98"])
    station = st.selectbox("Tankstation", ["Shell", "BP", "Esso", "Texaco"])

    totaal = liters * prijs

    st.metric("Totaal prijs", f"€ {totaal:.2f}")

    if st.button("Opslaan"):

        lat, lon = None, None
        if gps:
            lat, lon = gps.split(",")

        auth = get_auth_client()

        res = auth.table("tankbeurten").insert({
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

        st.session_state.reset = True
        st.rerun()

# -------------------------
# DASHBOARD
# -------------------------
def dashboard():

    st.subheader("Dashboard")

    auth = get_auth_client()
    data = auth.table("tankbeurten").select("*").execute().data

    if not data:
        st.info("Geen data")
        return

    df = pd.DataFrame(data)

    df = df.drop(columns=["id", "user_id", "latitude", "longitude"], errors="ignore")

    st.dataframe(df, use_container_width=True)

    df["datum"] = pd.to_datetime(df["datum"])
    df = df.sort_values("datum")

    st.subheader("Kosten verloop")
    st.line_chart(df.set_index("datum")["totaal"])

    if "latitude" in data[0]:
        map_df = pd.DataFrame(data).dropna(subset=["latitude", "longitude"])
        if not map_df.empty:
            st.map(map_df.rename(columns={"latitude": "lat", "longitude": "lon"}))

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