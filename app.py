import streamlit as st
import pandas as pd
import gspread

# === Auth: dukung Cloud (st.secrets) & Lokal (file JSON) ===
# - Di Streamlit Cloud: taruh seluruh JSON service account di Secrets sebagai key "gcp_service_account"
# - Di lokal: pakai path file JSON kamu di LOCAL_CREDENTIAL_PATH
from google.oauth2.service_account import Credentials as GCredentials
from oauth2client.service_account import ServiceAccountCredentials as OCredentials  # fallback lokal

from peta import tampilkan_peta
from visualisasi import tampilkan_visualisasi


st.set_page_config(layout="wide", page_title="Dashboard Telkom", page_icon="📊")

# ---------------- Google Sheets auth ----------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

LOCAL_CREDENTIAL_PATH = "D:/Semester/Semester7/Magang/tlkm-project-75b00278557c.json"  # <- punyamu
SHEET_KEY = "1Cd9vbcHwFcq8rSARG7Kh7iNomFh5o8tVrEo946DbqX8"  # sheet yang sama

def _make_gspread_client() -> gspread.Client:
    """Buat client gspread. Prioritas: st.secrets (Cloud) lalu fallback ke file lokal."""
    try:
        # Streamlit Cloud: pakai secrets
        sa_info = st.secrets["gcp_service_account"]
        creds = GCredentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        # Lokal: pakai oauth2client + file JSON
        scope_legacy = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = OCredentials.from_json_keyfile_name(LOCAL_CREDENTIAL_PATH, scope_legacy)
        return gspread.authorize(creds)

client = _make_gspread_client()
sheet = client.open_by_key(SHEET_KEY).sheet1

# ---------------- Utilities ----------------
@st.cache_data(ttl=180)
def load_from_sheet() -> pd.DataFrame:
    """Ambil semua data dari Google Sheets -> DataFrame (tanpa ubah nama kolom)."""
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
        # Peta: tidak menampilkan tabel
        tampilkan_peta(df)
    elif page.startswith("📊"):
        # Rekap: tidak menampilkan tabel
        tampilkan_visualisasi(df)
    elif page.startswith("🧾"):
        # HANYA di sini tabel ditampilkan (nama tetap: Data mentah)
        st.subheader("Data mentah")
        st.dataframe(df, use_container_width=True)
