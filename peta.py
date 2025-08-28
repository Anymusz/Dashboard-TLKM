# peta.py — kontrol Peta muncul di container sidebar yang dikirim dari app.py
import re, pandas as pd, folium, streamlit as st
from folium.plugins import HeatMap, MarkerCluster
import streamlit.components.v1 as components

# --- helper kolom & parser singkat ---
def _pick_col_fuzzy(df, want="lat"):
    cand = {"lat":["lat","latitude","y"], "lon":["lon","longitude","lng","long","x"]}
    for c in cand[want]:
        if c in df.columns: return c
    pat = r"lat" if want=="lat" else r"lon|lng|long"
    for c in df.columns:
        if re.search(pat, c): return c
    return None

# ---------- UI ----------
def tampilkan_peta(df: pd.DataFrame, sidebar: st.delta_generator.DeltaGenerator|None=None):
    st.subheader("Peta Interaktif")

    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()

    # coba pecah kolom gabungan bila perlu
    if not {"lat","lon"}.issubset(df.columns):
        for c in df.columns:
            s = df[c].astype(str).str.replace(";", ",")
            m = s.str.extract(r'^\s*POINT\s*\(\s*([\-0-9\.,]+)\s+([\-0-9\.,]+)\s*\)\s*$', expand=True)
            if m.notna().all(axis=None):
                try:
                    df["lon"] = pd.to_numeric(m[0].str.replace(",", ".", regex=False), errors="coerce")
                    df["lat"] = pd.to_numeric(m[1].str.replace(",", ".", regex=False), errors="coerce")
                    break
                except: pass
            parts = s.str.replace(r'[\[\]\(\)]',' ',regex=True).str.split(r'[,\s]+', expand=True)
            if parts.shape[1] >= 2:
                try:
                    lat = pd.to_numeric(parts[0].str.replace(",", ".", regex=False), errors="coerce")
                    lon = pd.to_numeric(parts[1].str.replace(",", ".", regex=False), errors="coerce")
                    if lat.notna().sum()>0 and lon.notna().sum()>0:
                        df["lat"], df["lon"] = lat, lon
                        break
                except: pass

    lat_col = _pick_col_fuzzy(df,"lat"); lon_col = _pick_col_fuzzy(df,"lon")
    tgl_col = next((c for c in df.columns if c in ["tanggal","tgl","date","waktu"] or "tanggal" in c or "date" in c), None)
    status_col = next((c for c in df.columns if "status" in c or c in ["keterangan","info"]), None)
    sto_col = next((c for c in df.columns if "sto" in c), None)
    sektor_col = next((c for c in df.columns if c in ["sektor","sector"] or "sektor" in c or "sector" in c), None)

    if not lat_col or not lon_col:
        st.warning("Tidak ada lat/lon yang valid.")
        st.dataframe(df.head(10))
        return

    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    # ====== KONTROL DI SIDEBAR (container dari app.py) ======
    holder = sidebar if sidebar is not None else st.sidebar
    with holder:
        st.markdown("#### Pengaturan Peta")
        vis_mode = st.radio("Tampilan", ["Titik dengan Profil", "Heatmap"],
                            horizontal=True, key="map_vis_mode")

        # pusat peta: kab/kota Jambi
        kabupaten_coords = {
            "Batang Hari": (-1.70, 103.08), "Bungo": (-1.60, 102.13), "Kerinci": (-2.18, 101.50),
            "Merangin": (-2.08, 101.4747), "Muaro Jambi": (-1.73, 103.61), "Sarolangun": (-2.30, 102.70),
            "Tanjung Jabung Barat": (-0.79, 103.46), "Tanjung Jabung Timur": (-1.20, 103.90),
            "Tebo": (-1.490917, 102.445194), "Kota Jambi": (-1.61, 103.61), "Kota Sungai Penuh": (-2.06, 101.39),
        }
        opt_center = st.selectbox("Pilih Kabupaten/Kota (Jambi) untuk pusat peta",
                                  ["(Gunakan tengah data)"] + list(kabupaten_coords.keys()),
                                  index=0, key="opt_center")

        # filter atribut ringan
        if sto_col:
            sel_sto = st.multiselect("Filter STO", sorted(df[sto_col].dropna().astype(str).unique()), key="flt_sto")
        else:
            sel_sto = []
        if sektor_col:
            sel_sek = st.multiselect("Filter Sektor", sorted(df[sektor_col].dropna().astype(str).unique()), key="flt_sek")
        else:
            sel_sek = []

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
        center_lat = df[lat_col].mean(); center_lon = df[lon_col].mean(); zoom_start = 7

    # siapkan data + filter
    subset_cols = [lat_col, lon_col]
    for c in [tgl_col, status_col, sto_col, sektor_col]:
        if c: subset_cols.append(c)
    data_valid = df[subset_cols].dropna(subset=[lat_col, lon_col])
    if sel_sto: data_valid = data_valid[data_valid[sto_col].astype(str).isin(sel_sto)]
    if sel_sek: data_valid = data_valid[data_valid[sektor_col].astype(str).isin(sel_sek)]

    # peta
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
        if heat: HeatMap(heat, radius=15, blur=10, max_zoom=1).add_to(m)

    # output
    if no_rerun: components.html(m.get_root().render(), height=500, scrolling=False)
    else:        st_folium(m, width=900, height=500, key="map_main")
