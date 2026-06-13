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
    name, country_year, country_month, fuel_mix_month, fuel_mix_wide,
    hourly_profile, prices_month, geojson, available_countries,
    fit_europe_map, EUROPE_CENTER, EUROPE_ZOOM, MAP_STYLE, MONTH_NAMES_ES,
)
from src.config import FUEL_GROUPS, FUEL_GROUP_COLORS, PM25_YEARS

st.set_page_config(page_title="Evolución", page_icon="📈", layout="wide")
st.title("Evolución temporal")

# Controles 
countries = available_countries()
st.sidebar.header("Controles")
default = [c for c in ["DE", "FR", "PL", "ES", "NO"] if c in countries]
selected = st.sidebar.multiselect(
    "Países a comparar", countries, default=default, format_func=name)
yr_min, yr_max = min(PM25_YEARS), max(PM25_YEARS)
yr_range = st.sidebar.slider("Rango de años", yr_min, yr_max, (yr_min, yr_max))
focus = st.sidebar.selectbox(
    "País para mezcla y perfil horario", countries,
    index=countries.index(default[0]) if default else 0, format_func=name)

if not selected:
    st.info("Selecciona al menos un país en la barra lateral.")
    st.stop()

# 1) Serie multipaís de intensidad de carbono
st.subheader("① Intensidad de carbono mensual")
cm = country_month()
mask = (cm["country"].isin(selected)) & (cm["year"].between(*yr_range))
ci_ts = cm[mask].copy()
ci_ts["País"] = ci_ts["country"].map(name)
fig1 = px.line(
    ci_ts.sort_values("date"), x="date", y="carbon_intensity_mean", color="País",
    labels={"date": "", "carbon_intensity_mean": "gCO₂/kWh"},
    title="Intensidad de carbono de la electricidad (media mensual)",
)
fig1.update_layout(height=400, hovermode="x unified", legend_title="")
fig1.update_traces(hovertemplate="%{y:.0f} gCO₂/kWh")
st.plotly_chart(fig1, width="stretch", config=PLOTLY_CONFIG)
st.caption(
    "Tendencia descendente = descarbonización. Los picos invernales reflejan mayor "
    "uso de carbón/gas cuando cae la generación solar."
)

st.divider()

# 2) Mezcla de generación apilada (país foco)
st.subheader(f"② Mezcla de generación — {name(focus)}")
fm = fuel_mix_month()
fm_f = fm[(fm["country"] == focus) & (fm["year"].between(*yr_range))]
groups = [g for g in FUEL_GROUPS if g in fm_f["fuel_group"].unique()]
view = st.radio("Unidades", ["Absoluta (GWh)", "Relativa (%)"], horizontal=True)
wide = fuel_mix_wide(fm_f, ["date"]).sort_values("date")
if view.startswith("Relativa"):
    tot = wide[groups].sum(axis=1).replace(0, np.nan)
    for g in groups:
        wide[g] = wide[g] / tot * 100
    ylab = "% de la generación"
else:
    ylab = "GWh / mes"
fig2 = go.Figure()
for g in groups:
    fig2.add_trace(go.Scatter(
        x=wide["date"], y=wide[g], name=g, mode="lines", stackgroup="one",
        line=dict(width=0.5, color=FUEL_GROUP_COLORS[g]),
        hovertemplate=f"{g}: %{{y:.0f}}<extra></extra>",
    ))
fig2.update_layout(
    height=420, title=f"Composición de la generación eléctrica — {name(focus)}",
    yaxis_title=ylab, hovermode="x unified", legend_title="Fuente",
)
st.plotly_chart(fig2, width="stretch", config=PLOTLY_CONFIG)

st.divider()

# 3) Mapa animado de intensidad de carbono por año 
st.subheader("③ Mapa animado: intensidad de carbono año a año")
cy = country_year()
cy_anim = cy[cy["year"].between(*yr_range)].dropna(subset=["carbon_intensity_mean"]).copy()
cy_anim["pais"] = cy_anim["country"].map(name)
fig3 = px.choropleth_map(
    cy_anim.sort_values("year"),
    geojson=geojson(),
    locations="country", featureidkey="properties.NUTS_ID",
    color="carbon_intensity_mean", animation_frame="year",
    color_continuous_scale="YlOrRd", range_color=(0, cy_anim["carbon_intensity_mean"].max()),
    hover_name="pais", labels={"carbon_intensity_mean": "gCO₂/kWh"}, opacity=0.78,
    center=EUROPE_CENTER, zoom=EUROPE_ZOOM, map_style=MAP_STYLE,
)
fit_europe_map(fig3, height=560)
fig3.update_layout(coloraxis_colorbar=dict(title="gCO₂/kWh", thickness=14, len=0.7))
st.plotly_chart(fig3, width="stretch", config=PLOTLY_CONFIG)
st.caption("Pulsa ▶ para ver la evolución. Observa cómo varios países se aclaran con los años.")

st.divider()

# 4) Mapa de calor hora × mes (perfil de carbono)
st.subheader(f"④ Perfil horario de intensidad de carbono — {name(focus)}")
hp = hourly_profile()
hp_f = hp[hp["country"] == focus]
if hp_f.empty:
    st.info("Sin datos de perfil horario para este país.")
else:
    pivot = hp_f.pivot_table(index="hour", columns="month",
                             values="carbon_intensity_mean")
    pivot = pivot.reindex(index=range(24), columns=range(1, 13))
    fig4 = px.imshow(
        pivot, color_continuous_scale="YlOrRd", aspect="auto",
        labels=dict(x="Mes", y="Hora del día", color="gCO₂/kWh"),
        x=[MONTH_NAMES_ES[m - 1] for m in pivot.columns], y=list(pivot.index),
    )
    fig4.update_layout(height=440, title=f"Intensidad de carbono media por hora y mes — {name(focus)}")
    fig4.update_yaxes(autorange="reversed")
    st.plotly_chart(fig4, width="stretch", config=PLOTLY_CONFIG)
    st.caption(
        "Las franjas claras del mediodía revelan el efecto solar; las oscuras nocturnas, "
        "la dependencia de fuentes fósiles cuando no hay sol."
    )

st.divider()

# 6) Precios y volatilidad 
st.subheader("⑤ Precio mayorista y volatilidad")
pm = prices_month()
pmask = (pm["country"].isin(selected)) & (pm["year"].between(*yr_range))
pr = pm[pmask].copy()
if pr.empty:
    st.info("Sin datos de precios para la selección.")
else:
    pr["País"] = pr["country"].map(name)
    fig5 = px.line(
        pr.sort_values("date"), x="date", y="price_mean", color="País",
        labels={"date": "", "price_mean": "€/MWh"},
        title="Precio medio mensual del mercado día-anterior",
    )
    fig5.update_layout(height=400, hovermode="x unified", legend_title="")
    st.plotly_chart(fig5, width="stretch", config=PLOTLY_CONFIG)
    st.caption(
        "La crisis energética de 2022 dispara los precios. La eólica y la solar reducen "
        "tanto el precio medio como su volatilidad."
    )
