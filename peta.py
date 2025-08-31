# peta.py — peta interaktif + pembersihan koordinat & autoswap untuk data Jambi
import re
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import streamlit as st

# ---------- util geo ----------
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
        except: return (None, None)
    m = _DMS_RE.match(s)
    if m:
        try:
            lat = _dms_to_dd(m.group("lat_deg"), m.group("lat_min"), m.group("lat_sec"), m.group("lat_hem"))
            lon = _dms_to_dd(m.group("lon_deg"), m.group("lon_min"), m.group("lon_sec"), m.group("lon_hem"))
            return (lat, lon)
        except: return (None, None)
    return (None, None)

# —— NORMALISASI ANGKA KOORDINAT ——
def _coerce_coord(val: object, kind: str) -> float | None:
    """
    LAT (Jambi ~ -1..-3):
      - '-12,148376' -> '-12.148376'
      - |lat| > 6 -> bagi 10 berulang: -12.148376 -> -1.2148376
    LON (Indonesia 95..141):
      - '1.037.952.395' -> '1037952395'
      - turunkan skala sampai 95..141: 1037952395 -> 103.7952395
    """
    if val is None: return None
    s = str(val).strip().replace(" ", "")
    if not s or s.lower() in ("nan","none","null","-"): return None

    if "," in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    else:
        if s.count(".") > 1:
            s = s.replace(".", "")

    if s in ("", "+", "-"): return None

    if "." in s:
        try:
            v = float(s)
        except Exception:
            return None
    else:
        sign = -1.0 if s.startswith("-") else 1.0
        digits = re.sub(r"[^0-9]", "", s)
        if not digits: return None
        base = float(digits)
        n = len(digits)
        if kind == "lon":
            scale_pow = max(n - 3, 0)   # 103.xxx
        else:
            scale_pow = max(n - 2, 0)   # 1.x / 2.x
        v = sign * (base / (10 ** scale_pow))

    if kind == "lat":
        while abs(v) > 6:
            v /= 10.0
    else:
        while v > 141:
            v /= 10.0
        while v < 95 and v > 0.95:
            v *= 10.0
        if v < -180 or v > 180:
            return None

    return v

def _pick_col_fuzzy(df, want="lat"):
    candidates_exact = {
        "lat": ["lat", "latitude", "y", "koordinat_y", "coord_y"],
        "lon": ["lon", "longitude", "lng", "long", "x", "koordinat_x", "coord_x"],
    }
    for c in candidates_exact[want]:
        if c in df.columns: return c
    pattern = r"lat" if want == "lat" else r"lon|lng|long"
    for c in df.columns:
        if re.search(pattern, c): return c
    if want == "lat" and "y" in df.columns: return "y"
    if want == "lon" and "x" in df.columns: return "x"
    return None

# ---------- UI ----------
def tampilkan_peta(df: pd.DataFrame):
    st.subheader("Peta Interaktif")

    df = df.copy()
    # normalisasi header untuk deteksi, tampilan tabel tidak dipakai di halaman ini
    df.columns = df.columns.str.strip().str.lower()

    # pecah kolom gabungan kalau ada
    if not {"lat","lon"}.issubset(df.columns):
        cand = [c for c in df.columns if any(k in c for k in
                ["koordinat","coord","coordinate","latlon","tikor","lokasi","geotag","geom","geo","maps","map"])]
        if not cand: cand = [c for c in df.columns if df[c].dtype==object]
        best, ok = None, 0
        for c in cand:
            ser = df[c].astype(str)
            sample = ser.sample(min(200, len(ser)), random_state=0) if len(ser)>0 else ser
            hits = sum(1 for v in sample if _parse_coord_cell(v)[0] is not None)
            if hits>ok: ok, best = hits, c
        if best and ok>0:
            lat_vals, lon_vals = zip(*[_parse_coord_cell(v) for v in df[best].astype(str)])
            df["lat"] = pd.to_numeric(pd.Series(lat_vals), errors="coerce")
            df["lon"] = pd.to_numeric(pd.Series(lon_vals), errors="coerce")

    lat_col = _pick_col_fuzzy(df, "lat")
    lon_col = _pick_col_fuzzy(df, "lon")

    tgl_col    = next((c for c in df.columns if "tanggal" in c or "date" in c or c in ["tgl","waktu"]), None)
    status_col = next((c for c in df.columns if "status" in c or c in ["status sc","status_sc","keterangan","info"]), None)
    sto_col    = next((c for c in df.columns if "sto" in c), None)
    sektor_col = next((c for c in df.columns if "sektor" in c or "sector" in c), None)

    if not lat_col or not lon_col:
        st.warning("Tidak ada kolom lat/lon yang bisa dipakai.")
        return

    # ===== Normalisasi koordinat =====
    df[lat_col] = df[lat_col].map(lambda v: _coerce_coord(v, "lat"))
    df[lon_col] = df[lon_col].map(lambda v: _coerce_coord(v, "lon"))

    # Autoswap per baris (kalau kebolak-balik)
    mask_swap = (
        df[lat_col].between(95, 141, inclusive="both") &
        df[lon_col].between(-90, 90, inclusive="both")
    )
    if mask_swap.any():
        tmp = df.loc[mask_swap, lat_col].copy()
        df.loc[mask_swap, lat_col] = df.loc[mask_swap, lon_col]
        df.loc[mask_swap, lon_col] = tmp

    # Filter valid
    subset_cols = [lat_col, lon_col]
    for c in [tgl_col, status_col, sto_col, sektor_col]:
        if c: subset_cols.append(c)
    data_valid = df[subset_cols].dropna(subset=[lat_col, lon_col])

    # ===== Center peta =====
    with st.sidebar:
        st.markdown("### ⚙️ Pengaturan Peta")
        kabupaten_coords = {
            "Batang Hari": (-1.70, 103.08), "Bungo": (-1.60, 102.13), "Kerinci": (-2.18, 101.50),
            "Merangin": (-2.08, 101.4747), "Muaro Jambi": (-1.73, 103.61), "Sarolangun": (-2.30, 102.70),
            "Tanjung Jabung Barat": (-0.79, 103.46), "Tanjung Jabung Timur": (-1.20, 103.90),
            "Tebo": (-1.490917, 102.445194), "Kota Jambi": (-1.61, 103.61), "Kota Sungai Penuh": (-2.06, 101.39),
        }
        opt_center = st.selectbox("Pilih Kabupaten/Kota",
                                  ["(Gunakan tengah data)"] + list(kabupaten_coords.keys()),
                                  index=0, key="map_center")

    if opt_center != "(Gunakan tengah data)":
        center_lat, center_lon = kabupaten_coords[opt_center]; zoom_start = 11
    else:
        if not data_valid.empty:
            center_lat = data_valid[lat_col].mean()
            center_lon = data_valid[lon_col].mean()
        else:
            center_lat, center_lon = (-1.61, 103.61)
        zoom_start = 8

    # ===== Render peta =====
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start)
    cluster = MarkerCluster().add_to(m)

    for _, row in data_valid.iterrows():
        tanggal_val = row.get(tgl_col, "N/A") if tgl_col else "N/A"
        status_val  = row.get(status_col, "Tidak ada") if status_col else "Tidak ada"
        sto_val     = row.get(sto_col, "N/A") if sto_col else "N/A"
        sektor_val  = row.get(sektor_col, "N/A") if sektor_col else "N/A"
        popup_html = (
            "<div style='font-size:12px'>"
            f"<b>Tanggal:</b> {tanggal_val}<br>"
            f"<b>Status:</b> {status_val}<br>"
            f"<b>STO:</b> {sto_val}<br>"
            f"<b>Sektor:</b> {sektor_val}"
            "</div>"
        )
        folium.Marker([row[lat_col], row[lon_col]],
                      popup=popup_html,
                      icon=folium.Icon(color="red", icon="info-sign")).add_to(cluster)

    st.components.v1.html(m.get_root().render(), height=600, scrolling=False)
