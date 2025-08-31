import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from peta import tampilkan_peta
from visualisasi import tampilkan_visualisasi

st.set_page_config(layout="wide", page_title="Dashboard Telkom", page_icon="📊")

# ---------------- Google Sheets auth ----------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
# ⚠️ gunakan path credential milikmu
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "D:/Semester/Semester7/Magang/tlkm-project-75b00278557c.json", scope
)
client = gspread.authorize(creds)

# Open the Google Sheet by key (first worksheet)
sheet = client.open_by_key("1Cd9vbcHwFcq8rSARG7Kh7iNomFh5o8tVrEo946DbqX8").sheet1

# ---------------- Utilities ----------------
def load_from_sheet() -> pd.DataFrame:
    """Fetch all data from Google Sheets -> DataFrame (jaga header asli)."""
    data = sheet.get_all_records()
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
        # Peta: tidak tampilkan tabel
        tampilkan_peta(df)
    elif page.startswith("📊"):
        # Rekap: tidak tampilkan tabel
        tampilkan_visualisasi(df)
    elif page.startswith("🧾"):
        # HANYA di sini tabel ditampilkan (nama tetap: Data mentah)
        st.subheader("Data mentah")
        st.dataframe(df, use_container_width=True)
