# app.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials  # satu-satunya lib auth

from peta import tampilkan_peta
from visualisasi import tampilkan_visualisasi

st.set_page_config(layout="wide", page_title="Dashboard Telkom", page_icon="📊")

# ---- Google Sheets auth (Cloud via st.secrets, Lokal via file) ----
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# gunakan file kredensial hanya saat run lokal
LOCAL_CREDENTIAL_PATH = "D:/Semester/Semester7/Magang/tlkm-project-75b00278557c.json"
SHEET_KEY = "1Cd9vbcHwFcq8rSARG7Kh7iNomFh5o8tVrEo946DbqX8"

def _make_gspread_client() -> gspread.Client:
    # 1) Streamlit Cloud → ambil dari secrets
    try:
        sa_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        pass
    # 2) Lokal → ambil dari file json
    creds = Credentials.from_service_account_file(LOCAL_CREDENTIAL_PATH, scopes=SCOPES)
    return gspread.authorize(creds)

client = _make_gspread_client()
sheet = client.open_by_key(SHEET_KEY).sheet1

@st.cache_data(ttl=180)
def load_from_sheet() -> pd.DataFrame:
    data = sheet.get_all_records()  # list of dict
    return pd.DataFrame(data)

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("☰ Menu")
    df = load_from_sheet()
    st.write("Data has been loaded from Google Sheets.")
    page = st.radio("Pilih halaman", ["🗺️ Peta", "📊 Rekap", "🧾 Data mentah"], index=0)

# ---------------- Main ----------------
if df.empty:
    st.info("Tidak ada data yang tersedia.")
else:
    if page.startswith("🗺️"):
        tampilkan_peta(df)
    elif page.startswith("📊"):
        tampilkan_visualisasi(df)
    elif page.startswith("🧾"):
        st.subheader("Data mentah")
        st.dataframe(df, use_container_width=True)
