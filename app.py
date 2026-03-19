import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client
from supabase.lib.client_options import ClientOptions

# ------------------------
# CONFIG
# ------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------
# AUTH CLIENT (RLS FIX)
# ------------------------
def get_auth_client():
    if "session" not in st.session_state or st.session_state.session is None:
        return None

    access_token = st.session_state.session.session.access_token

    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            headers={
                "Authorization": f"Bearer {access_token}"
            }
        )
    )

# ------------------------
# SESSION INIT
# ------------------------
if "session" not in st.session_state:
    st.session_state.session = None

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "page" not in st.session_state:
    st.session_state.page = "login"

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

        except Exception:
            st.error("Login mislukt")

# ------------------------
# LOGOUT
# ------------------------
def logout():
    st.session_state.session = None
    st.session_state.user_id = None
    st.session_state.page = "login"
    st.rerun()

# ------------------------
# NAVIGATIE
# ------------------------
def navigation():
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Nieuwe tankbeurt"):
            st.session_state.page = "nieuw"

    with col2:
        if st.button("Dashboard"):
            st.session_state.page = "dashboard"

    with col3:
        if st.button("Logout"):
            logout()

# ------------------------
# NIEUWE TANKBEURT
# ------------------------
def nieuwe_tankbeurt():
    st.subheader("Nieuwe tankbeurt")

    datum = st.date_input("Datum", value=date.today())
    liters = st.number_input("Liters", min_value=0.0)
    prijs = st.number_input("Prijs per liter (€)", min_value=0.0)
    km = st.number_input("Gereden km", min_value=0.0)

    totaal = liters * prijs
    kosten_per_km = totaal / km if km > 0 else 0

    st.write(f"Totaal: €{totaal:.2f}")
    st.write(f"Kosten per km: €{kosten_per_km:.2f}")

    if st.button("Opslaan"):
        auth_supabase = get_auth_client()

        if not auth_supabase:
            st.error("Niet ingelogd")
            return

        try:
            auth_supabase.table("tankbeurten").insert({
                "user_id": st.session_state.user_id,
                "datum": str(datum),
                "liters": liters,
                "prijs": prijs,
                "km": km,
                "totaal": totaal
            }).execute()

            st.success("Opgeslagen")

        except Exception as e:
            st.error("Opslaan mislukt (RLS?)")

# ------------------------
# DASHBOARD
# ------------------------
def dashboard():
    st.subheader("Dashboard")

    auth_supabase = get_auth_client()

    if not auth_supabase:
        st.error("Niet ingelogd")
        return

    try:
        res = auth_supabase.table("tankbeurten").select("*").execute()
        data = res.data

        if not data:
            st.warning("Geen data beschikbaar")
            return

        df = pd.DataFrame(data)

        # Verberg interne kolommen
        df_display = df.drop(columns=["id", "user_id"], errors="ignore")

        st.dataframe(df_display, use_container_width=True)

        # Analyse
        totaal_kosten = df["totaal"].sum()
        totaal_km = df["km"].sum()

        st.write(f"Totale kosten: €{totaal_kosten:.2f}")

        if totaal_km > 0:
            st.write(f"Gemiddeld € per km: €{totaal_kosten / totaal_km:.2f}")

        # ------------------------
        # DELETE
        # ------------------------
        st.subheader("Verwijderen")

        ids = df["id"].tolist()
        selected_id = st.selectbox("Selecteer record", ids)

        if st.button("Verwijder"):
            auth_supabase.table("tankbeurten") \
                .delete() \
                .eq("id", selected_id) \
                .execute()

            st.success("Verwijderd")
            st.rerun()

    except Exception as e:
        st.error("Fout bij ophalen data")

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

    else:
        st.title("Welkom")