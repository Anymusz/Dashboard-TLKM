# peta.py — kontrol Peta di sidebar (tanpa radius), pusat kabupaten, filter STO/Sektor
import re
import pandas as pd
import folium
from folium.plugins import HeatMap, MarkerCluster
import streamlit as st
import streamlit.components.v1 as components

# --------- helper ----------
def _pick_col_fuzzy(df, want="lat"):
    cand = {"lat": ["lat", "latitude", "y"], "lon": ["lon", "longitude", "lng", "long", "x"]}
    for c in cand[want]:
        if c in df.columns: return c
    pat = r"lat" if want == "lat" else r"lon|lng|long"
    for c in df.columns:
        if re.search(pat, c): return c
    return None

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
    if len(parts) == 2 and all(re.match(r'^-?\d+(?:[\.,]\d+)?$', p) for p in parts):
        try: return (float(parts[0].replace(",", ".")), float(parts[1].replace(",", ".")))
        except: return (None, None)
    return (None, None)

def _pick_kab_col(df):
    for c in df.columns:
        lc = str(c).lower()
        if any(k in lc for k in ["kabupaten", "kab.", "kab ", "kota"]):
            return c
    return None

# --------- UI ----------
def tampilkan_peta(df: pd.DataFrame, sidebar=None):
    st.subheader("Peta Interaktif")

    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()

    # pecah kolom koordinat gabungan bila perlu
    if not {"lat", "lon"}.issubset(df.columns):
        for c in df.columns:
            latlon = df[c].astype(str)
            # POINT(lon lat)
            ext = latlon.str.extract(r'^\s*POINT\s*\(\s*([\-0-9\.,]+)\s+([\-0-9\.,]+)\s*\)\s*$', expand=True)
            if ext.notna().all(axis=None):
                try:
                    df["lon"] = pd.to_numeric(ext[0].str.replace(",", ".", regex=False), errors="coerce")
                    df["lat"] = pd.to_numeric(ext[1].str.replace(",", ".", regex=False), errors="coerce")
                    break
                except:
                    pass
            # "lat,lon" / "lat lon"
            parts = latlon.str.replace(r'[\[\]\(\)]', ' ', regex=True).str.split(r'[,\s]+', expand=True)
            if parts.shape[1] >= 2:
                lat = pd.to_numeric(parts[0].str.replace(",", ".", regex=False), errors="coerce")
                lon = pd.to_numeric(parts[1].str.replace(",", ".", regex=False), errors="coerce")
                if lat.notna().sum() > 0 and lon.notna().sum() > 0:
                    df["lat"], df["lon"] = lat, lon
                    break

    lat_col = _pick_col_fuzzy(df, "lat")
    lon_col = _pick_col_fuzzy(df, "lon")
    if not lat_col or not lon_col:
        st.warning("Tidak ada lat/lon yang valid.")
        st.dataframe(df.head(10))
        return

    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    tgl_col    = next((c for c in df.columns if c in ["tanggal","tgl","date","waktu"] or "tanggal" in c or "date" in c), None)
    status_col = next((c for c in df.columns if "status" in c or c in ["keterangan","info"]), None)
    sto_col    = next((c for c in df.columns if "sto" in c), None)
    sektor_col = next((c for c in df.columns if c in ["sektor","sector"] or "sektor" in c or "sector" in c), None)
    kab_data_col = _pick_kab_col(df)

    # ===== Kontrol di sidebar (pakai container dari app.py bila ada) =====
    holder = sidebar if sidebar is not None else st.sidebar
    with holder:
        st.markdown("#### Pengaturan Peta")
        vis_mode = st.radio("Tampilan", ["Titik dengan Profil", "Heatmap"], horizontal=True, key="map_vis_mode")

        kabupaten_coords = {
            "Batang Hari": (-1.70, 103.08), "Bungo": (-1.60, 102.13),
            "Kerinci": (-2.18, 101.50), "Merangin": (-2.08, 101.4747),
            "Muaro Jambi": (-1.73, 103.61), "Sarolangun": (-2.30, 102.70),
            "Tanjung Jabung Barat": (-0.79, 103.46), "Tanjung Jabung Timur": (-1.20, 103.90),
            "Tebo": (-1.490917, 102.445194), "Kota Jambi": (-1.61, 103.61),
            "Kota Sungai Penuh": (-2.06, 101.39),
        }
        opt_center = st.selectbox(
            "Pilih Kabupaten/Kota (Jambi) untuk pusat peta",
            ["(Gunakan tengah data)"] + list(kabupaten_coords.keys()),
            index=0, key="map_center"
        )

        st.markdown("### 🔎 Filter Data")
        sel_kab = []
        if kab_data_col:
            vals = sorted([v for v in df[kab_data_col].dropna().astype(str).unique() if v.strip()])
            sel_kab = st.multiselect("Kabupaten (dari data)", vals, default=[], key="flt_kab")
        sel_sto = []
        if sto_col:
            vals = sorted([v for v in df[sto_col].dropna().astype(str).unique() if v.strip()])
            sel_sto = st.multiselect("STO", vals, default=[], key="flt_sto")
        sel_sek = []
        if sektor_col:
            vals = sorted([v for v in df[sektor_col].dropna().astype(str).unique() if v.strip()])
            sel_sek = st.multiselect("Sektor", vals, default=[], key="flt_sek")

        no_rerun = st.checkbox("Jangan rerun saat gerak peta", value=True, key="map_quiet")

    # pusat dan zoom
    if opt_center != "(Gunakan tengah data)":
        center_lat, center_lon = kabupaten_coords[opt_center]
        radius_deg = 0.5
        nearby = df[(df[lat_col].between(center_lat - radius_deg, center_lat + radius_deg)) &
                    (df[lon_col].between(center_lon - radius_deg, center_lon + radius_deg))]
        n_points = len(nearby)
        zoom_start = 13 if n_points > 1000 else 12 if n_points > 200 else 11 if n_points > 50 else 10
    else:
        center_lat = df[lat_col].mean()
        center_lon = df[lon_col].mean()
        zoom_start = 7

    # data untuk plot + filter atribut
    subset_cols = [lat_col, lon_col]
    for c in [tgl_col, status_col, sto_col, sektor_col, kab_data_col]:
        if c: subset_cols.append(c)
    data_valid = df[subset_cols].dropna(subset=[lat_col, lon_col])

    if kab_data_col and sel_kab:
        data_valid = data_valid[data_valid[kab_data_col].astype(str).isin(sel_kab)]
    if sto_col and sel_sto:
        data_valid = data_valid[data_valid[sto_col].astype(str).isin(sel_sto)]
    if sektor_col and sel_sek:
        data_valid = data_valid[data_valid[sektor_col].astype(str).isin(sel_sek)]

    # render peta
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, width="100%", height=500)

    if vis_mode == "Titik dengan Profil":
        cluster = MarkerCluster().add_to(m)
        shown = 0
        for _, row in data_valid.iterrows():
            tanggal_val = row.get(tgl_col, "N/A") if tgl_col else "N/A"
            status_val  = row.get(status_col, "Tidak ada") if status_col else "Tidak ada"
            sto_val     = row.get(sto_col, "N/A") if sto_col else "N/A"
            sektor_val  = row.get(sektor_col, "N/A") if sektor_col else "N/A"
            html = (f"<b>Tanggal:</b> {tanggal_val}<br>"
                    f"<b>Status:</b> {status_val}<br>"
                    f"<b>STO:</b> {sto_val}<br>"
                    f"<b>Sektor:</b> {sektor_val}")
            folium.Marker([row[lat_col], row[lon_col]],
                          popup=html, icon=folium.Icon(color="red", icon="info-sign")).add_to(cluster)
            shown += 1
        st.caption(f"Menampilkan {shown} titik.")
    else:
        heat = data_valid[[lat_col, lon_col]].values.tolist()
        if heat:
            HeatMap(heat, radius=15, blur=10, max_zoom=1).add_to(m)
            st.info(f"Total titik pada peta: **{len(heat)}**")
        else:
            st.warning("Tidak ada data koordinat valid untuk Heatmap.")

    # output: non-rerun atau interaktif default
    if no_rerun:
        components.html(m.get_root().render(), height=500, scrolling=False)
    else:
        from streamlit_folium import st_folium
        st_folium(m, width=900, height=500, key="map_main")
