# app.py — sidebar terstruktur + injeksi container untuk kontrol halaman
import streamlit as st
import pandas as pd
import re
from peta import tampilkan_peta
from visualisasi import tampilkan_visualisasi

st.set_page_config(layout="wide", page_title="Dashboard Analisis Kendala Operasional Telkom", page_icon="📊")
st.title("Dashboard Analisis Kendala Operasional Telkom")

# --- util ringkas (dibiarin sama) ---
def _read_csv_any_sep(file): return pd.read_csv(file, sep=None, engine="python")
def _fmt_int(n):
    try: return f"{int(n):,}".replace(",", ".")
    except: return str(n)
def _detect_date_col(columns):
    for c in columns:
        lc = str(c).strip().lower()
        if lc in ("tanggal","tgl","date","waktu") or "tanggal" in lc or "date" in lc: return c
    return None

# ============ SIDEBAR ============
with st.sidebar:
    st.header("☰ Menu")

    # 1) Upload
    uploaded_file = st.file_uploader("📂 Upload file CSV", type=["csv"])
    if uploaded_file is not None:
        df = _read_csv_any_sep(uploaded_file)
        # normalisasi minimal
        df.columns = df.columns.str.strip().str.lower()
        st.session_state["data"] = df
        st.success("✅ Data berhasil diunggah!")

    # 2) Navigasi
    page = st.radio("Pilih halaman", ["🗺️ Peta", "📊 Rekap", "🧾 Data mentah"], index=0)

    # 3) TEMPAT WAJIB untuk kontrol halaman (akan diisi fungsi halaman)
    st.markdown("---")
    st.subheader("⚙️ Pengaturan")
    sidebar_controls = st.container()   # >>> ini yang kita kirim ke halaman

    # 4) Ringkasan data (di bawah kontrol halaman)
    if "data" in st.session_state:
        df_side = st.session_state["data"]
        with st.expander("🧠 Ringkasan data", expanded=True):
            n_rows, n_cols = df_side.shape
            c1, c2 = st.columns(2)
            c1.metric("Baris", _fmt_int(n_rows))
            c2.metric("Kolom", _fmt_int(n_cols))
            tcol = _detect_date_col(df_side.columns)
            if tcol:
                dates = pd.to_datetime(df_side[tcol], errors="coerce").dropna()
                if not dates.empty:
                    st.caption(f"Rentang tanggal: **{dates.min().strftime('%m-%d-%Y')} – {dates.max().strftime('%m-%d-%Y')}**")

# ============ KONTEN ============
if "data" not in st.session_state:
    st.info("Silakan upload file CSV di sidebar.")
else:
    df = st.session_state["data"]
    if page.startswith("🗺️"):
        tampilkan_peta(df, sidebar=sidebar_controls)    # >>> kirim container sidebar
    elif page.startswith("📊"):
        tampilkan_visualisasi(df)
    else:
        st.subheader("Data mentah")
        st.dataframe(df, use_container_width=True)
