# app.py — sidebar lebar global + nav di area utama + support kolom tikor gabungan
import streamlit as st
import pandas as pd
import re
from io import BytesIO
from peta import tampilkan_peta
from visualisasi import tampilkan_visualisasi

st.set_page_config(layout="wide", page_title="Dashboard Analisis Kendala Operasional Telkom", page_icon="📊")

# ⇩ CSS: lebar sidebar global
st.markdown("""
<style>
section[data-testid="stSidebar"]{width:360px !important}
</style>
""", unsafe_allow_html=True)

# Ubah judul utama
st.title("Dashboard Analisis Kendala Operasional Telkom")

# ---------- Util tambahan ----------
_DMS_RE = re.compile(r"""(?ix)^\s*(?P<lat_deg>-?\d+(?:\.\d+)?)\s*[°d:\s]?\s*
(?P<lat_min>\d+(?:\.\d+)?)?\s*[\'m:\s]?\s*
(?P<lat_sec>\d+(?:\.\d+)?)?\s*(?P<lat_hem>[NS])?[,\s/]+
(?P<lon_deg>-?\d+(?:\.\d+)?)\s*[°d:\s]?\s*
(?P<lon_min>\d+(?:\.\d+)?)?\s*[\'m:\s]?\s*
(?P<lon_sec>\d+(?:\.\d+)?)?\s*(?P<lon_hem>[EW])?\s*$""")

def _dms_to_dd(deg, minute=None, second=None, hem=None):
    v = float(deg)
    if minute: v += float(minute)/60.0
    if second: v += float(second)/3600.0
    if hem:
        hem = hem.upper()
        v = -abs(v) if hem in ("S","W") else abs(v)
    return v

def _parse_coord_cell(txt):
    if txt is None: return (None, None)
    s = str(txt).strip()
    if not s or s.lower() in ("nan","none","null","-"): return (None, None)
    m = re.match(r'^\s*POINT\s*\(\s*([\-0-9\.,]+)\s+([\-0-9\.,]+)\s*\)\s*$', s, flags=re.I)
    if m:
        lon = m.group(1).replace(",", "."); lat = m.group(2).replace(",", ".")
        try: return (float(lat), float(lon))
        except: return (None, None)
    s2 = re.sub(r'[\[\]\(\)]', ' ', s.replace(";", ","))
    parts = [p for p in re.split(r'[,\s]+', s2.strip()) if p]
    if len(parts)==2 and all(re.match(r'^-?\d+(?:[\.,]\d+)?$', p) for p in parts):
        try: return (float(parts[0].replace(",", ".")), float(parts[1].replace(",", ".")))
        except: pass
    m = _DMS_RE.match(s)
    if m:
        try:
            lat = _dms_to_dd(m.group("lat_deg"), m.group("lat_min"), m.group("lat_sec"), m.group("lat_hem"))
            lon = _dms_to_dd(m.group("lon_deg"), m.group("lon_min"), m.group("lon_sec"), m.group("lon_hem"))
            return (lat, lon)
        except: return (None, None)
    return (None, None)

def _split_single_coord_column(df):
    if {"lat","lon"}.issubset(df.columns): return df
    cand = [c for c in df.columns if any(k in c for k in
            ["koordinat","coord","coordinate","latlon","tikor","lokasi","geotag","geom","geo","maps","map"])]
    if not cand: cand = [c for c in df.columns if df[c].dtype==object]
    best, ok = None, 0
    for c in cand:
        ser = df[c].astype(str)
        sample = ser.sample(min(50, len(ser)), random_state=0) if len(ser)>0 else ser
        hits = sum(1 for v in sample if _parse_coord_cell(v)[0] is not None)
        if hits>ok: ok, best = hits, c
    if best and ok>0:
        lat_vals, lon_vals = zip(*[_parse_coord_cell(v) for v in df[best].astype(str)])
        df["lat"] = pd.to_numeric(pd.Series(lat_vals), errors="coerce")
        df["lon"] = pd.to_numeric(pd.Series(lon_vals), errors="coerce")
    return df

# ---------- Util ----------
def _read_csv_any_sep(file):
    return pd.read_csv(file, sep=None, engine="python")

def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    rename_map = {
        "latitude": "lat", "lat": "lat", "y": "lat",
        "longitude": "lon", "lng": "lon", "long": "lon", "x": "lon",
        "tanggal": "tanggal", "tgl": "tanggal", "date": "tanggal", "waktu": "tanggal",
    }
    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})
    df = _split_single_coord_column(df)
    for col in ("lat", "lon"):
        if col in df.columns and df[col].dtype == object:
            df[col] = (df[col].astype(str)
                       .str.replace(",", ".", regex=False)
                       .str.replace(r"[^0-9\.\-]", "", regex=True))
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def _fmt_int(n):
    try: return f"{int(n):,}".replace(",", ".")
    except Exception: return str(n)

def _detect_date_col(columns):
    for c in columns:
        lc = str(c).strip().lower()
        if lc in ("tanggal","tgl","date","waktu") or "tanggal" in lc or "date" in lc:
            return c
    return None

# ---------- Sidebar (global) ----------
with st.sidebar:
    st.header("☰ Menu")
    uploaded_file = st.file_uploader("📂 Upload file CSV", type=["csv"])
    if uploaded_file is not None:
        df = _read_csv_any_sep(uploaded_file)
        df = _normalize_cols(df)
        st.session_state["data"] = df
        st.session_state["page"] = "🗺️ Peta"
        st.success("✅ Data berhasil diunggah!")

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

# ---------- Nav di area utama ----------
if "page" not in st.session_state:
    st.session_state["page"] = "🗺️ Peta"

opsi = ["🗺️ Peta", "📊 Rekap", "🧾 Data mentah"]
idx_awal = opsi.index(st.session_state["page"])
page = st.radio("Halaman", opsi, index=idx_awal, horizontal=True, label_visibility="collapsed", key="nav_main")
st.session_state["page"] = page

# ---------- Konten utama ----------
if "data" not in st.session_state:
    st.info("Silakan upload file CSV di sidebar.")
else:
    df = st.session_state["data"]
    if page == "🗺️ Peta":
        if {"lat","lon"}.issubset(df.columns):
            tampilkan_peta(df)
        else:
            st.warning("Kolom `lat`/`lon` tidak ditemukan. Peta tidak bisa ditampilkan.")
            st.dataframe(df, use_container_width=True)
    elif page == "📊 Rekap":
        tampilkan_visualisasi(df)
    else:
        st.subheader("Data mentah")
        st.dataframe(df, use_container_width=True)
