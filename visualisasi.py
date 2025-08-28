# visualisasi.py — Rekap Historis (Harian/Mingguan) + opsi tampilan + DOWNLOAD (kontrol di sidebar)
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

DATE_FMT = "%m-%d-%Y"

def _detect_date_col(columns):
    for c in columns:
        lc = str(c).strip().lower()
        if lc in ("tanggal", "tgl", "date", "waktu") or "tanggal" in lc or "date" in lc:
            return c
    return None

def _zscore_outliers(s: pd.Series, win: int = 7, z_thr: float = 2.0) -> pd.Series:
    roll_mean = s.rolling(win, min_periods=win).mean()
    roll_std  = s.rolling(win, min_periods=win).std()
    z = (s - roll_mean) / roll_std
    return (roll_std > 0) & (z > z_thr)

def _fmt(n: float) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return str(n)

def tampilkan_visualisasi(df: pd.DataFrame):
    st.subheader("Rekap Historis — Harian / Mingguan")

    # ---------- siapkan data harian ----------
    df = df.copy()
    df.columns = df.columns.str.strip()

    tgl_col = _detect_date_col(df.columns)
    if not tgl_col:
        st.warning("Kolom tanggal tidak ditemukan.")
        st.write("Kolom tersedia:", df.columns.tolist())
        return

    df[tgl_col] = pd.to_datetime(df[tgl_col], errors="coerce").dt.tz_localize(None)
    df = df.dropna(subset=[tgl_col])

    y_daily = (
        df.set_index(tgl_col)
          .resample("D").size()
          .asfreq("D").fillna(0)
          .rename("jumlah_harian")
    )
    if y_daily.empty:
        st.info("Tidak ada data untuk ditampilkan.")
        return

    # ====== SIDEBAR ======
    with st.sidebar:
        st.markdown("### ⚙️ Pengaturan Visualisasi")

        mode = st.radio("Mode rekap", ["Harian", "Mingguan"], horizontal=True, key="viz_mode")

        opsi_semua = ["Titik data", "Garis median", "Tandai lonjakan", "Mode gelap"]
        dipilih = st.multiselect("Tampilan grafik", opsi_semua, default=opsi_semua, key="viz_opts")

        col_from, col_to = st.columns(2)
        with col_from:
            start_date = st.date_input("Dari", value=y_daily.index.min().date(), key="viz_from")
        with col_to:
            end_date = st.date_input("Sampai", value=y_daily.index.max().date(), key="viz_to")

    if pd.to_datetime(start_date) > pd.to_datetime(end_date):
        st.warning("Tanggal mulai harus sebelum tanggal akhir.")
        return

    y_daily = y_daily.loc[str(start_date):str(end_date)]

    # opsi
    show_points     = "Titik data" in st.session_state["viz_opts"]
    show_median     = "Garis median" in st.session_state["viz_opts"]
    highlight_spike = "Tandai lonjakan" in st.session_state["viz_opts"]
    dark            = "Mode gelap" in st.session_state["viz_opts"]

    # ---------- angka ringkas ----------
    last_val = int(y_daily.iloc[-1]) if len(y_daily) else 0
    prev_val = int(y_daily.iloc[-2]) if len(y_daily) > 1 else 0
    last7 = int(y_daily.tail(7).sum()) if len(y_daily) else 0
    prev7 = int(y_daily.iloc[:-7].tail(7).sum()) if len(y_daily) > 7 else 0
    wow = ((last7 - prev7) / prev7 * 100.0) if prev7 > 0 else np.nan
    top_day = y_daily.idxmax() if len(y_daily) else None
    top_val = int(y_daily.max()) if len(y_daily) else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Hari terakhir", _fmt(last_val))
    m2.metric("Sehari sebelumnya", _fmt(prev_val), f"{last_val - prev_val:+}")
    m3.metric("Total 7 hari terakhir", _fmt(last7),
              None if np.isnan(wow) else f"{wow:+.1f}% vs 7 hari sebelumnya")
    m4.metric("Tertinggi di periode", _fmt(top_val),
              top_day.strftime(DATE_FMT) if top_day is not None else "-")

    # ---------- seri sesuai mode ----------
    if mode == "Harian":
        x = y_daily.index
        y = y_daily.values
        title = "Jumlah Harian"
        hover = "<b>%{x|%m-%d-%Y}</b><br>Jumlah: %{y}<extra></extra>"
        median_val = np.median(y_daily.values)
        spikes_mask = _zscore_outliers(y_daily) if highlight_spike else pd.Series(False, index=y_daily.index)
    else:
        weekly = y_daily.resample("W-MON").sum().rename("total_mingguan")
        weekly = weekly.loc[str(start_date):str(end_date)]
        x = weekly.index
        y = weekly.values
        title = "Jumlah Mingguan (total)"
        hover = "<b>%{x|%m-%d-%Y}</b><br>Total minggu: %{y}<extra></extra>"
        median_val = np.median(weekly.values) if len(weekly) else 0
        spikes_mask = _zscore_outliers(weekly) if highlight_spike else pd.Series(False, index=weekly.index)

    # ---------- grafik ----------
    template = "plotly_dark" if dark else "plotly_white"
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x, y=y, name=title,
        mode="lines+markers" if show_points else "lines",
        line=dict(width=1.6),
        marker=dict(size=4, line=dict(width=0)),
        hovertemplate=hover
    ))

    if show_median and len(y) > 0:
        fig.add_hline(
            y=median_val, line_width=1, line_dash="dot",
            annotation_text=f"Median ~ {median_val:.0f}", annotation_position="top left"
        )

    if highlight_spike and spikes_mask.any():
        xs = pd.Index(x)[spikes_mask.values]
        ys = np.array(y)[spikes_mask.values]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, name="Lonjakan",
            mode="markers", marker=dict(size=8, symbol="diamond-open"),
            hovertemplate=hover
        ))

    if len(y) > 0:
        peak_idx = int(np.argmax(y)); peak_x, peak_y = x[peak_idx], y[peak_idx]
        fig.add_trace(go.Scatter(x=[peak_x], y=[peak_y], mode="markers",
                                 name="Puncak", marker=dict(size=9, symbol="star", line=dict(width=0))))
        fig.add_annotation(x=peak_x, y=peak_y, text=f"Puncak: {_fmt(peak_y)}",
                           showarrow=True, arrowhead=2, yshift=12)

    fig.update_layout(
        template=template,
        title=dict(text=f"{title} (Rekap {pd.to_datetime(start_date).strftime(DATE_FMT)} – {pd.to_datetime(end_date).strftime(DATE_FMT)})", x=0.5),
        xaxis=dict(title="Tanggal", tickformat="%m-%d-%Y", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
        yaxis=dict(title="Jumlah", showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---------- tabel + unduh ----------
    if mode == "Harian":
        out = pd.DataFrame({"Tanggal": pd.Index(x).strftime(DATE_FMT), "Jumlah": y})
    else:
        out = pd.DataFrame({"Akhir Minggu": pd.Index(x).strftime(DATE_FMT), "Total Mingguan": y})

    st.dataframe(out, use_container_width=True)

    start_str = pd.to_datetime(start_date).strftime(DATE_FMT)
    end_str   = pd.to_datetime(end_date).strftime(DATE_FMT)
    stem = f"rekap_{'harian' if mode=='Harian' else 'mingguan'}_{start_str}_sd_{end_str}"

    csv_bytes = out.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Unduh CSV", data=csv_bytes, file_name=f"{stem}.csv", mime="text/csv", use_container_width=True)
