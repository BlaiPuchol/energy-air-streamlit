import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from app.components import (
    PLOTLY_CONFIG,
    name, available_countries, live_generation, live_carbon_all,
    fuel_mix_donut, carbon_gauge, choropleth, country_centroids,
    live_pm25_europe, pm25_points_map, openaq_available,
    pm25_quality, PM25_QUALITY_LEVELS,
)
from src.config import FUEL_GROUPS, FUEL_GROUP_COLORS

st.set_page_config(page_title="Tiempo real", page_icon="📡", layout="wide")
st.title("Europa en tiempo real")
st.markdown(
    "Generación eléctrica en vivo (API *Energy-Charts* / Fraunhofer ISE) y **PM2.5 medida "
    "en tiempo real** (API *OpenAQ*). Los datos se cachean 15 min para no saturar los servicios."
)

countries = available_countries()
RANGES = {"Últimas 24 h": 1, "Última semana": 7, "Último mes": 30}
st.sidebar.header("Controles")
default = "ES" if "ES" in countries else countries[0]
country = st.sidebar.selectbox(
    "País", countries, index=countries.index(default), format_func=name)
range_label = st.sidebar.selectbox("Periodo", list(RANGES.keys()))
days = RANGES[range_label]
if st.sidebar.button("Forzar actualización"):
    st.cache_data.clear()
    st.rerun()

# Detalle del país seleccionado
with st.spinner(f"Consultando generación en vivo de {name(country)} ({range_label.lower()})…"):
    df, source = live_generation(country, days=days)

badge = {"fraunhofer": "En vivo (Energy-Charts)",
         "entsoe": "En vivo (ENTSO-E)",
         None: "Sin datos en vivo"}.get(source, "Sin datos en vivo")

if df.empty:
    st.error(
        f"No hay generación en vivo disponible para {name(country)} en este momento. "
        "Prueba con otro país o usa el botón de actualización."
    )
else:
    ts = df.index.max()
    fuel_cols = [c for c in df.columns if c not in
                 ("total_generation_mw", "total_emissions_gco2",
                  "carbon_intensity_gco2_kwh", "renewable_share")]
    shares = {}
    for group, cols in FUEL_GROUPS.items():
        present = [c for c in cols if c in fuel_cols]
        if present:
            val = float(df[present].clip(lower=0).mean().sum())
            if val > 0:
                shares[group] = val

    ci_last = df["carbon_intensity_gco2_kwh"].dropna()
    ren_last = df["renewable_share"].dropna()
    gen_last = df["total_generation_mw"].dropna()

    st.success(f"{badge} · datos hasta `{ts:%Y-%m-%d %H:%M %Z}`")

    k1, k2, k3 = st.columns(3)
    k1.metric("Generación actual", f"{gen_last.iloc[-1]/1000:.1f} GW" if len(gen_last) else "N/D")
    k2.metric("Cuota renovable", f"{ren_last.iloc[-1]*100:.0f} %" if len(ren_last) else "N/D")
    k3.metric("Intensidad de carbono", f"{ci_last.iloc[-1]:.0f} gCO₂/kWh" if len(ci_last) else "N/D")

    c1, c2 = st.columns([1, 1])
    with c1:
        if len(ci_last):
            st.plotly_chart(carbon_gauge(ci_last.iloc[-1]), width="stretch", config=PLOTLY_CONFIG)
    with c2:
        st.plotly_chart(
            fuel_mix_donut(shares, title=f"Mezcla media ({range_label.lower()}) — {name(country)}"),
            width="stretch", config=PLOTLY_CONFIG,
        )

    # Área apilada de la generación en vivo por grupo.
    st.subheader(f"Generación por fuente — {range_label.lower()}")
    groups_present = list(shares.keys())
    melt_rows = []
    for group in groups_present:
        cols = [c for c in FUEL_GROUPS[group] if c in fuel_cols]
        series = df[cols].clip(lower=0).sum(axis=1)
        for t, v in series.items():
            melt_rows.append({"time": t, "Fuente": group, "MW": v})
    area = pd.DataFrame(melt_rows)
    fig_area = go.Figure()
    for group in groups_present:
        sub = area[area["Fuente"] == group]
        fig_area.add_trace(go.Scatter(
            x=sub["time"], y=sub["MW"], name=group, mode="lines", stackgroup="one",
            line=dict(width=0.5, color=FUEL_GROUP_COLORS[group]),
            hovertemplate=f"{group}: %{{y:.0f}} MW<extra></extra>",
        ))
    fig_area.update_layout(height=380, yaxis_title="MW", hovermode="x unified",
                           legend_title="Fuente", margin=dict(t=20))
    st.plotly_chart(fig_area, width="stretch", config=PLOTLY_CONFIG)

    # Evolución de la intensidad de carbono en el periodo.
    st.subheader(f"Intensidad de carbono — {range_label.lower()}")
    if len(ci_last):
        ci_df = ci_last.rename("gCO₂/kWh").reset_index()
        ci_df.columns = ["Fecha", "gCO₂/kWh"]
        fig_ci = px.line(ci_df, x="Fecha", y="gCO₂/kWh",
                         labels={"Fecha": ""})
        fig_ci.update_traces(line_color="#e74c3c")
        fig_ci.update_layout(height=340, hovermode="x unified", margin=dict(t=20))
        st.plotly_chart(fig_ci, width="stretch", config=PLOTLY_CONFIG)
        st.caption(
            "Intensidad de carbono = emisiones (gCO₂) / energía generada (kWh), "
            "usando factores de emisión por tipo de fuente (IPCC AR6)."
        )

st.divider()

# Mapa europeo en vivo
st.subheader("Intensidad de carbono ahora mismo en Europa")
st.caption(
    "Mapa de todos los países con datos en vivo (respaldo a la media del último año "
    "donde la API no responde). Puede tardar unos segundos en la primera carga."
)
if st.button("Cargar / actualizar mapa europeo en vivo"):
    st.session_state.show_eu_map = True

if st.session_state.get("show_eu_map"):
    with st.spinner("Consultando todos los países…"):
        allc = live_carbon_all(countries)
    if allc.empty:
        st.warning("No se han podido obtener datos.")
    else:
        hist = allc[allc["source"] == "historical"]
        n_live = len(allc) - len(hist)
        fig_map = choropleth(
            allc, "carbon_intensity_mean",
            title="Intensidad de carbono en vivo (gCO₂/kWh)", unit="gCO₂/kWh",
            colorscale="YlOrRd",
            hover_extra={"renewable_share_mean": ":.0%", "source": True},
        )
        # Marca los países sin datos en vivo (respaldo histórico) con un punto negro.
        if not hist.empty:
            cents = country_centroids()
            marked = [(name(c), cents[c][0], cents[c][1])
                      for c in hist["country"] if c in cents]
            if marked:
                labels, lats, lons = zip(*marked)
                fig_map.add_trace(go.Scattermap(
                    lat=list(lats), lon=list(lons), mode="markers",
                    marker=dict(size=12, color="#1a1a1a"),
                    name="Sin datos en vivo (media histórica)",
                    hovertext=[f"{l} · dato histórico" for l in labels],
                    hoverinfo="text",
                ))
                fig_map.update_layout(
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=0.0, x=0.0,
                                bgcolor="rgba(255,255,255,0.75)"),
                )
        st.caption(
            f"🟢 **{n_live}/{len(allc)}** países con datos en vivo · "
            f"⚫ **{len(hist)}** con media histórica (marcados con un punto negro)."
        )
        st.plotly_chart(fig_map, width="stretch", config=PLOTLY_CONFIG)
else:
    st.info("Pulsa el botón para construir el mapa europeo (varias llamadas a la API).")

st.divider()

# Calidad del aire en vivo (OpenAQ)
st.subheader("Calidad del aire ahora mismo — PM2.5 (OpenAQ)")
st.markdown(
    "Mediciones de **PM2.5 en tiempo real** en estaciones europeas, vía la API de "
    "[OpenAQ](https://openaq.org). Complementa la generación: aquí se ve el resultado "
    "—el aire que se respira— de cómo se produce la energía."
)

if not openaq_available():
    st.info(
        "Define `OPENAQ_API_KEY` (en `.streamlit/secrets.toml` o como variable de "
        "entorno) para activar la capa de calidad del aire en vivo. Es gratuita: "
        "regístrate en https://openaq.org."
    )
else:
    if st.button("Cargar / actualizar calidad del aire en vivo"):
        st.session_state.show_aq = True

    if st.session_state.get("show_aq"):
        with st.spinner("Consultando estaciones de OpenAQ…"):
            aq = live_pm25_europe()
        if aq.empty:
            st.warning("OpenAQ no ha devuelto mediciones recientes en este momento.")
        else:
            WHO_24H = 15  # directriz OMS 2021 para PM2.5 (media 24 h, µg/m³)
            n_sta = len(aq)
            median = aq["pm25"].median()
            exceed = int((aq["pm25"] > WHO_24H).sum())
            last_ts = pd.to_datetime(aq["datetime"], errors="coerce").max()

            m1, m2, m3 = st.columns(3)
            m1.metric("Estaciones reportando", f"{n_sta}")
            m2.metric("PM2.5 mediana", f"{median:.1f} µg/m³")
            m3.metric("Superan directriz OMS 24 h", f"{exceed} ({exceed/n_sta*100:.0f} %)",
                      help="OMS 2021: 15 µg/m³ de media en 24 h.")

            # Filtro por calidad del aire (la escala de color se mantiene fija con el máximo real).
            aq = aq.copy()
            aq["calidad"] = aq["pm25"].apply(pm25_quality)
            sel_levels = st.multiselect(
                "Filtrar por calidad del aire", PM25_QUALITY_LEVELS,
                default=PM25_QUALITY_LEVELS,
            )
            import math
            vmax = min(100.0, max(25.0, math.ceil(float(aq["pm25"].max()) / 5) * 5))
            aq_view = aq[aq["calidad"].isin(sel_levels)] if sel_levels else aq.iloc[0:0]

            if aq_view.empty:
                st.info("Ninguna estación coincide con el filtro seleccionado.")
            else:
                st.plotly_chart(pm25_points_map(aq_view, vmax=vmax),
                                width="stretch", config=PLOTLY_CONFIG)
            st.caption(
                f"Mostrando **{len(aq_view)}/{n_sta}** estaciones. Cada punto es una estación; "
                f"el color indica su PM2.5 más reciente (verde = aire limpio → rojo = contaminación "
                f"elevada, escala 0–{vmax:.0f} µg/m³). Datos hasta `{last_ts:%Y-%m-%d %H:%M} UTC` aprox. "
                f"Directriz OMS de referencia: {WHO_24H} µg/m³ en 24 h."
            )
    else:
        st.info("Pulsa el botón para superponer las estaciones de PM2.5 en vivo.")
