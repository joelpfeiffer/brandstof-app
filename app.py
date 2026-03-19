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
# SESSION INIT
# -------------------------
defaults = {
    "user": None,
    "session": None,
    "liters": 0.0,
    "prijs": 0.0,
    "km": 0.0,
    "brandstof": "euro 95",
    "station": "Shell"
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# -------------------------
# AUTH CLIENT (VEILIG)
# -------------------------
def get_auth_client():
    session = st.session_state.session

    if session is None or not hasattr(session, "access_token"):
        st.error("Niet ingelogd / session fout")
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
    except Exception as e:
        st.warning(f"OCR niet actief: {e}")
        return None

vision_client = get_vision_client()

# -------------------------
# OCR PARSER (GOED)
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

            st.success("Ingelogd")
            st.rerun()

        except Exception as e:
            st.error(e)

# -------------------------
# NIEUWE ENTRY
# -------------------------
def nieuwe():

    st.subheader("Nieuwe tankbeurt")

    uploaded = st.file_uploader("Upload bon", type=["jpg", "png", "jpeg"])

    if uploaded and vision_client:
        image = vision.Image(content=uploaded.read())
        response = vision_client.text_detection(image=image)
        text = response.text_annotations[0].description if response.text_annotations else ""

        st.text_area("OCR tekst", text, height=120)

        l, p = parse_bon(text)

        if l:
            st.session_state.liters = l
        if p:
            st.session_state.prijs = p

    st.number_input("Liters", key="liters")
    st.number_input("Prijs per liter", key="prijs")
    st.number_input("KM", key="km")

    st.selectbox("Brandstof", ["euro 95", "diesel", "euro 98"], key="brandstof")
    st.selectbox("Tankstation", ["Shell", "BP", "Esso", "Texaco"], key="station")

    totaal = st.session_state.liters * st.session_state.prijs
    st.metric("Totaal", f"€ {totaal:.2f}")

    if st.button("Opslaan"):

        auth = get_auth_client()
        if auth is None:
            return

        try:
            lat, lon = None, None
            if gps:
                lat, lon = gps.split(",")

            res = auth.table("tankbeurten").insert({
                "user_id": st.session_state.user.id,
                "datum": str(datetime.today().date()),
                "liters": st.session_state.liters,
                "prijs": st.session_state.prijs,
                "km": st.session_state.km,
                "totaal": totaal,
                "brandstof": st.session_state.brandstof,
                "station": st.session_state.station,
                "latitude": lat,
                "longitude": lon
            }).execute()

            st.write(res)  # DEBUG
            st.success("Opgeslagen")

            # RESET
            st.session_state.liters = 0.0
            st.session_state.prijs = 0.0
            st.session_state.km = 0.0
            st.session_state.brandstof = "euro 95"
            st.session_state.station = "Shell"

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
        res = auth.table("tankbeurten").select("*").execute()
        st.write(res)  # DEBUG

        data = res.data

        if not data:
            st.warning("Geen data")
            return

        df = pd.DataFrame(data)

        df = df.drop(columns=["id", "user_id", "latitude", "longitude"], errors="ignore")

        st.dataframe(df, use_container_width=True)

        df["datum"] = pd.to_datetime(df["datum"])
        df = df.sort_values("datum")

        st.line_chart(df.set_index("datum")["totaal"])

        map_df = pd.DataFrame(data).dropna(subset=["latitude", "longitude"])
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