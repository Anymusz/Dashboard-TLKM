# visualisasi.py — Rekap Harian/Mingguan + opsi tampilan (sidebar, tanpa tombol mass select)
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

DATE_FMT = "%m-%d-%Y"

def _detect_date_col(columns):
    for c in columns:
        lc = str(c).strip().lower()
        if lc in ("tanggal","tgl","date","waktu") or "tanggal" in lc or "date" in lc:
            return c
    return None

def _zscore_outliers(s: pd.Series, win: int = 7, z_thr: float = 2.0) -> pd.Series:
    roll_mean = s.rolling(win, min_periods=win).mean()
    roll_std  = s.rolling(win, min_periods=win).std()
    z = (s - roll_mean) / roll_std
    return (roll_std > 0) & (z > z_thr)

def _fmt(n: float) -> str:
    try: return f"{int(n):,}".replace(",", ".")
    except: return str(n)

def tampilkan_visualisasi(df: pd.DataFrame):
    st.subheader("Rekap Historis — Harian / Mingguan")

    for k, v in {"opt_points": True, "opt_median": True, "opt_spike": True,
                 "opt_dark": False, "viz_mode": "Harian"}.items():
        if k not in st.session_state: st.session_state[k] = v

    df = df.copy()
    df.columns = df.columns.str.strip()
    tgl_col = _detect_date_col(df.columns)
    if not tgl_col:
        st.warning("Kolom tanggal tidak ditemukan."); return

    df[tgl_col] = pd.to_datetime(df[tgl_col], errors="coerce").dt.tz_localize(None)
    df = df.dropna(subset=[tgl_col])

    y_daily = (df.set_index(tgl_col).resample("D").size()
                 .asfreq("D").fillna(0).rename("jumlah_harian"))
    if y_daily.empty:
        st.info("Tidak ada data untuk ditampilkan."); return

    with st.sidebar:
        st.markdown("### ⚙️ Pengaturan Visualisasi")
        mode = st.radio("Mode rekap", ["Harian","Mingguan"], horizontal=True, key="viz_mode")
        st.markdown("**Tampilan grafik**")
        show_points     = st.checkbox("Titik data", key="opt_points")
        show_median     = st.checkbox("Garis median", key="opt_median")
        highlight_spike = st.checkbox("Tandai lonjakan", key="opt_spike")
        dark            = st.toggle("Mode gelap (grafik)", key="opt_dark")
        c1, c2 = st.columns(2)
        with c1: start_date = st.date_input("Dari",  value=y_daily.index.min().date(), key="viz_from")
        with c2: end_date   = st.date_input("Sampai", value=y_daily.index.max().date(), key="viz_to")

    if pd.to_datetime(start_date) > pd.to_datetime(end_date):
        st.warning("Tanggal mulai harus sebelum tanggal akhir."); return

    y_daily = y_daily.loc[str(start_date):str(end_date)]

    last_val = int(y_daily.iloc[-1]) if len(y_daily) else 0
    prev_val = int(y_daily.iloc[-2]) if len(y_daily)>1 else 0
    last7 = int(y_daily.tail(7).sum()) if len(y_daily) else 0
    prev7 = int(y_daily.iloc[:-7].tail(7).sum()) if len(y_daily)>7 else 0
    import numpy as np
    wow = ((last7-prev7)/prev7*100) if prev7>0 else np.nan
    top_day = y_daily.idxmax() if len(y_daily) else None
    top_val = int(y_daily.max()) if len(y_daily) else 0

    a,b,c,d = st.columns(4)
    a.metric("Hari terakhir", _fmt(last_val))
    b.metric("Sehari sebelumnya", _fmt(prev_val), f"{last_val-prev_val:+}")
    c.metric("Total 7 hari", _fmt(last7), None if np.isnan(wow) else f"{wow:+.1f}%")
    d.metric("Tertinggi", _fmt(top_val), top_day.strftime(DATE_FMT) if top_day is not None else "-")

    if st.session_state["viz_mode"] == "Harian":
        x = y_daily.index; y = y_daily.values
        title = "Jumlah Harian"
        hover = "<b>%{x|%m-%d-%Y}</b><br>Jumlah: %{y}<extra></extra>"
        median_val = np.median(y_daily.values)
        def _z(s): 
            roll_mean = s.rolling(7, min_periods=7).mean()
            roll_std  = s.rolling(7, min_periods=7).std()
            z = (s - roll_mean) / roll_std
            return (roll_std > 0) & (z > 2.0)
        spikes_mask = _z(y_daily) if st.session_state["opt_spike"] else pd.Series(False, index=y_daily.index)
    else:
        weekly = y_daily.resample("W-MON").sum().rename("total_mingguan")
        weekly = weekly.loc[str(start_date):str(end_date)]
        x = weekly.index; y = weekly.values
        title = "Jumlah Mingguan (total)"
        hover = "<b>%{x|%m-%d-%Y}</b><br>Total minggu: %{y}<extra></extra>"
        median_val = np.median(weekly.values) if len(weekly) else 0
        def _z(s): 
            roll_mean = s.rolling(7, min_periods=7).mean()
            roll_std  = s.rolling(7, min_periods=7).std()
            z = (s - roll_mean) / roll_std
            return (roll_std > 0) & (z > 2.0)
        spikes_mask = _z(weekly) if st.session_state["opt_spike"] else pd.Series(False, index=weekly.index)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, name=title,
        mode="lines+markers" if st.session_state["opt_points"] else "lines",
        line=dict(width=1.6), marker=dict(size=4, line=dict(width=0)),
        hovertemplate=hover
    ))
    if st.session_state["opt_median"] and len(y)>0:
        fig.add_hline(y=median_val, line_width=1, line_dash="dot",
                      annotation_text=f"Median ~ {median_val:.0f}", annotation_position="top left")
    if st.session_state["opt_spike"] and spikes_mask.any():
        xs = pd.Index(x)[spikes_mask.values]; ys = np.array(y)[spikes_mask.values]
        fig.add_trace(go.Scatter(x=xs, y=ys, name="Lonjakan", mode="markers",
                                 marker=dict(size=8, symbol="diamond-open"), hovertemplate=hover))

    if len(y)>0:
        i = int(np.argmax(y))
        fig.add_trace(go.Scatter(x=[x[i]], y=[y[i]], mode="markers",
                                 name="Puncak", marker=dict(size=9, symbol="star")))
        fig.add_annotation(x=x[i], y=y[i], text=f"Puncak: {_fmt(y[i])}",
                           showarrow=True, arrowhead=2, yshift=12)

    fig.update_layout(
        template="plotly_dark" if st.session_state["opt_dark"] else "plotly_white",
        title=dict(text=f"{title} (Rekap {pd.to_datetime(start_date).strftime(DATE_FMT)} – {pd.to_datetime(end_date).strftime(DATE_FMT)})", x=0.5),
        xaxis=dict(title="Tanggal", tickformat="%m-%d-%Y", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
        yaxis=dict(title="Jumlah", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    out = (pd.DataFrame({"Tanggal": pd.Index(x).strftime(DATE_FMT), "Jumlah": y})
           if st.session_state["viz_mode"]=="Harian"
           else pd.DataFrame({"Akhir Minggu": pd.Index(x).strftime(DATE_FMT), "Total Mingguan": y}))
    st.dataframe(out, use_container_width=True)
    stem = f"rekap_{'harian' if st.session_state['viz_mode']=='Harian' else 'mingguan'}_" \
           f"{pd.to_datetime(start_date).strftime(DATE_FMT)}_sd_{pd.to_datetime(end_date).strftime(DATE_FMT)}"
    st.download_button("⬇️ Unduh CSV", data=out.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{stem}.csv", mime="text/csv", use_container_width=True)
