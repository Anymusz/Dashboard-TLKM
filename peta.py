# peta.py — semua pengaturan di sidebar
import re
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MarkerCluster
import streamlit as st
from math import radians, sin, cos, sqrt, atan2

# ---------- util geo ----------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

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

def _pick_col_fuzzy(df, want="lat"):
    cols = list(df.columns)
    candidates_exact = {
        "lat": ["lat", "latitude", "y", "koordinat_y", "coord_y"],
        "lon": ["lon", "longitude", "lng", "long", "x", "koordinat_x", "coord_x"],
    }
    for c in candidates_exact[want]:
        if c in df.columns: return c
    pattern = r"lat" if want == "lat" else r"lon|lng|long"
    for c in cols:
        if re.search(pattern, c): return c
    if want == "lat" and "y" in df.columns: return "y"
    if want == "lon" and "x" in df.columns: return "x"
    return None

# ---------- UI ----------
def tampilkan_peta(df: pd.DataFrame):
    st.subheader("Peta Interaktif")

    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()

    # pecah kolom tikor gabungan bila perlu
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

    tgl_col    = next((c for c in df.columns if c in ["tanggal","tgl","date","waktu"] or "tanggal" in c or "date" in c), None)
    status_col = next((c for c in df.columns if c in ["status sc","status_sc","status","keterangan","info"] or "status" in c), None)
    sto_col    = next((c for c in df.columns if c == "sto" or "sto" in c), None)
    sektor_col = next((c for c in df.columns if c in ["sektor","sector"] or "sektor" in c or "sector" in c), None)

    if not lat_col or not lon_col:
        st.warning("Tidak ada lat/lon yang valid.")
        st.dataframe(df.head(10))
        return

    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    center_lat = df[lat_col].mean(); center_lon = df[lon_col].mean()
    zoom_start = 7

    # ====== SIDEBAR: pengaturan peta ======
    with st.sidebar:
        st.markdown("### ⚙️ Pengaturan Peta")
        vis_mode = st.radio("Tampilan", ["Titik dengan Profil", "Heatmap"], horizontal=True)
        kabupaten_coords = {
            "Batang Hari": (-1.70, 103.08), "Bungo": (-1.60, 102.13), "Kerinci": (-2.18, 101.50),
            "Merangin": (-2.08, 101.4747), "Muaro Jambi": (-1.73, 103.61), "Sarolangun": (-2.30, 102.70),
            "Tanjung Jabung Barat": (-0.79, 103.46), "Tanjung Jabung Timur": (-1.20, 103.90),
            "Tebo": (-1.490917, 102.445194), "Kota Jambi": (-1.61, 103.61), "Kota Sungai Penuh": (-2.06, 101.39),
        }
        opt_center = st.selectbox("Pusat peta", ["(Gunakan tengah data)"] + list(kabupaten_coords.keys()), index=0)
        radius_km  = st.slider("Radius filter (km)", 5, 200, 50, step=5, key="radius_km")
        apply_btn  = st.button("Terapkan filter peta", key="btn_show_map")

    if opt_center != "(Gunakan tengah data)":
        center_lat, center_lon = kabupaten_coords[opt_center]
        radius_deg = 0.5
        nearby = df[(df[lat_col].between(center_lat - radius_deg, center_lat + radius_deg)) &
                    (df[lon_col].between(center_lon - radius_deg, center_lon + radius_deg))]
        n_points = len(nearby)
        zoom_start = 13 if n_points > 1000 else 12 if n_points > 200 else 11 if n_points > 50 else 10

    if apply_btn:
        st.session_state["fix_center"] = (center_lat, center_lon)
        st.session_state["show_filtered"] = True
    if "fix_center" not in st.session_state:
        st.session_state["fix_center"] = (center_lat, center_lon)
    if "show_filtered" not in st.session_state:
        st.session_state["show_filtered"] = False

    # ====== render ======
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start)
    subset_cols = [lat_col, lon_col]
    for c in [tgl_col, status_col, sto_col, sektor_col]:
        if c: subset_cols.append(c)
    data_valid = df[subset_cols].dropna(subset=[lat_col, lon_col])

    if vis_mode == "Titik dengan Profil":
        # jika filter aktif batasi radius
        if st.session_state["show_filtered"]:
            fc_lat, fc_lon = st.session_state["fix_center"]
            deg = st.session_state.get("radius_km", radius_km) / 111.0
            data_valid = data_valid[
                (data_valid[lat_col].between(fc_lat - deg, fc_lat + deg)) &
                (data_valid[lon_col].between(fc_lon - deg, fc_lon + deg))
            ]
        cluster = MarkerCluster().add_to(m)
        shown = 0
        for _, row in data_valid.iterrows():
            if st.session_state["show_filtered"]:
                jarak = haversine(st.session_state["fix_center"][0], st.session_state["fix_center"][1],
                                  row[lat_col], row[lon_col])
                if jarak > st.session_state.get("radius_km", radius_km): continue
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
            shown += 1
        if st.session_state["show_filtered"]:
            st.caption(f"Menampilkan {shown} titik dalam radius {st.session_state.get('radius_km', radius_km)} km.")
        else:
            st.caption(f"Menampilkan {shown} titik.")
    else:
        heat_data = data_valid[[lat_col, lon_col]].values.tolist()
        if heat_data:
            HeatMap(heat_data, radius=15, blur=10, max_zoom=1).add_to(m)
            st.info(f"Total titik pada peta: **{len(heat_data)}**")
        else:
            st.warning("Tidak ada data koordinat valid untuk Heatmap.")

    st_folium(m, width=900, height=500, key="map_main")
