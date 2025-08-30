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

# —— NORMALISASI ANGKA KOORDINAT (kebal format Eropa) ——
def _coerce_coord(val: object, kind: str) -> float | None:
    """
    Bersihkan angka koordinat dari berbagai format:
    - '1.037.952.395' -> 103.7952395  (titik ribuan dihapus, skala dikoreksi)
    - '-1,2148376'    -> -1.2148376   (koma sebagai desimal)
    - Buang simbol non-digit, spasi, dsb.
    kind: 'lat' | 'lon' untuk batas validasi (90 vs 180).
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-"):
        return None

    # Jika ada koma, asumsikan koma=desimal ⇒ hapus semua titik (ribuan) lalu ganti koma→titik
    if "," in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    else:
        # Tidak ada koma. Jika titik >1 (ribuan), hapus semua titik
        if s.count(".") > 1:
            s = s.replace(".", "")

    # Sisakan hanya tanda +/- dan titik desimal
    s = re.sub(r"[^0-9\.\-\+]", "", s)
    if s in ("", "+", "-"):
        return None

    try:
        v = float(s)
    except Exception:
        return None

    # Koreksi skala bila di luar rentang wajar (akibat ribuan)
    limit = 90.0 if kind == "lat" else 180.0
    while abs(v) > limit and abs(v) > 0:
        v /= 10.0

    return v

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
    # engine="python" dengan sep=None akan auto-deteksi delimiter (`,`/`;`/tab`)
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

    # 🔽 pecah kolom gabungan jika ada
    df = _split_single_coord_column(df)

    # 🔽 pembersihan kuat untuk lat/lon (tahan format Eropa)
    if "lat" in df.columns:
        df["lat"] = df["lat"].map(lambda v: _coerce_coord(v, "lat"))
    if "lon" in df.columns:
        df["lon"] = df["lon"].map(lambda v: _coerce_coord(v, "lon"))

    # 🔁 heuristik bila kolom ketuker (sering terjadi: lat ≈100, lon ≈-1..-2)
    if {"lat","lon"}.issubset(df.columns):
        lat_med = pd.to_numeric(pd.Series(df["lat"]), errors="coerce").abs().median()
        lon_med = pd.to_numeric(pd.Series(df["lon"]), errors="coerce").abs().median()
        if pd.notna(lat_med) and pd.notna(lon_med) and (lat_med > 90 and lon_med < 60):
            df["lat"], df["lon"] = df["lon"], df["lat"]

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
