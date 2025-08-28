# app.py — dengan sidebar navigasi & utilitas (support kolom tikor gabungan)
import streamlit as st
import pandas as pd
import re
from io import BytesIO
from peta import tampilkan_peta
from visualisasi import tampilkan_visualisasi

st.set_page_config(layout="wide", page_title="Dashboard Analisis Kendala Operasional Telkom", page_icon="📊")
st.title("Dashboard Analisis Kendala Operasional Telkom")

# ---------- Util tambahan ----------
_DMS_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?P<lat_deg>-?\d+(?:\.\d+)?)\s*[°d:\s]?\s*
    (?P<lat_min>\d+(?:\.\d+)?)?\s*[\'m:\s]?\s*
    (?P<lat_sec>\d+(?:\.\d+)?)?\s*(?P<lat_hem>[NS])?
    [,\s/]+
    (?P<lon_deg>-?\d+(?:\.\d+)?)\s*[°d:\s]?\s*
    (?P<lon_min>\d+(?:\.\d+)?)?\s*[\'m:\s]?\s*
    (?P<lon_sec>\d+(?:\.\d+)?)?\s*(?P<lon_hem>[EW])?
    \s*$
    """
)

def _dms_to_dd(deg, minute=None, second=None, hem=None):
    v = float(deg)
    if minute: v += float(minute)/60.0
    if second: v += float(second)/3600.0
    if hem:
        hem = hem.upper()
        if hem in ("S","W"): v = -abs(v)
        else: v = abs(v)
    return v

def _parse_coord_cell(txt):
    """Kembalikan (lat, lon) atau (None, None) dari string koordinat."""
    if txt is None: return (None, None)
    s = str(txt).strip()
    if not s or s.lower() in ("nan","none","null","-"): return (None, None)

    # format WKT POINT(lon lat)
    m = re.match(r'^\s*POINT\s*\(\s*([\-0-9\.,]+)\s+([\-0-9\.,]+)\s*\)\s*$', s, flags=re.I)
    if m:
        lon = m.group(1).replace(",", "."); lat = m.group(2).replace(",", ".")
        try: return (float(lat), float(lon))
        except: return (None, None)

    # format array/string: "lat,lon" / "lat lon" / "[lat, lon]"
    s2 = s.replace(";", ",")
    s2 = re.sub(r'[\[\]\(\)]', ' ', s2)
    parts = re.split(r'[,\s]+', s2.strip())
    parts = [p for p in parts if p]
    if len(parts) == 2 and all(re.match(r'^-?\d+(?:[\.,]\d+)?$', p) for p in parts):
        lat = parts[0].replace(",", "."); lon = parts[1].replace(",", ".")
        try: return (float(lat), float(lon))
        except: pass

    # format DMS
    m = _DMS_RE.match(s)
    if m:
        try:
            lat = _dms_to_dd(m.group("lat_deg"), m.group("lat_min"), m.group("lat_sec"), m.group("lat_hem"))
            lon = _dms_to_dd(m.group("lon_deg"), m.group("lon_min"), m.group("lon_sec"), m.group("lon_hem"))
            return (lat, lon)
        except: return (None, None)

    return (None, None)

def _split_single_coord_column(df):
    """Deteksi 1 kolom gabungan koordinat dan pecah jadi lat/lon."""
    if {"lat","lon"}.issubset(df.columns): 
        return df
    cand_names = [c for c in df.columns if any(k in c for k in [
        "koordinat","coord","coordinate","latlon","tikor","lokasi","geotag","geom","geo","maps","map"
    ])]
    if not cand_names:
        cand_names = [c for c in df.columns if df[c].dtype==object]
    best_col, ok = None, 0
    for c in cand_names:
        ser = df[c].astype(str)
        sample = ser.sample(min(50, len(ser)), random_state=0) if len(ser)>0 else ser
        hits = sum(1 for v in sample if _parse_coord_cell(v)[0] is not None)
        if hits > ok:
            ok, best_col = hits, c
    if best_col and ok>0:
        lat_vals, lon_vals = zip(*[ _parse_coord_cell(v) for v in df[best_col].astype(str) ])
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

    # 🔽 tambahkan pecah kolom gabungan
    df = _split_single_coord_column(df)

    for col in ("lat", "lon"):
        if col in df.columns and df[col].dtype == object:
            df[col] = (
                df[col].astype(str)
                    .str.replace(",", ".", regex=False)
                    .str.replace(r"[^0-9\.\-]", "", regex=True)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def _fmt_int(n):
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)

def _detect_date_col(columns):
    for c in columns:
        lc = str(c).strip().lower()
        if lc in ("tanggal", "tgl", "date", "waktu") or "tanggal" in lc or "date" in lc:
            return c
    return None

# ---------- Sidebar ----------
with st.sidebar:
    st.header("☰ Menu")
    uploaded_file = st.file_uploader("📂 Upload file CSV", type=["csv"])
    if uploaded_file is not None:
        df = _read_csv_any_sep(uploaded_file)
        df = _normalize_cols(df)
        st.session_state["data"] = df
        st.success("✅ Data berhasil diunggah!")

    page = st.radio("Pilih halaman", ["🗺️ Peta", "📊 Rekap", "🧾 Data mentah"], index=0)

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

# ---------- Konten utama ----------
if "data" not in st.session_state:
    st.info("Silakan upload file CSV di sidebar.")
else:
    df = st.session_state["data"]
    if page.startswith("🗺️"):
        if {"lat", "lon"}.issubset(df.columns):
            tampilkan_peta(df)
        else:
            st.warning("Kolom `lat`/`lon` tidak ditemukan. Peta tidak bisa ditampilkan.")
            st.dataframe(df, use_container_width=True)
    elif page.startswith("📊"):
        tampilkan_visualisasi(df)
    elif page.startswith("🧾"):
        st.subheader("Data mentah")
        st.dataframe(df, use_container_width=True)
