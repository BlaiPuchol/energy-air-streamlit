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
    name, available_countries, country_metrics_year, fuel_mix_year,
    pm25, hourly_profile, MONTH_NAMES_ES,
)
from src.config import FUEL_GROUP_COLORS, PM25_YEARS

st.set_page_config(page_title="Comparativa", page_icon="📊", layout="wide")
st.title("Comparativa de países")

countries = available_countries()
st.sidebar.header("Controles")
year = st.sidebar.slider("Año", min(PM25_YEARS), max(PM25_YEARS), max(PM25_YEARS))
default = [c for c in ["ES", "FR", "DE", "PL"] if c in countries]
selected = st.sidebar.multiselect("Países (radar)", countries, default=default, format_func=name)
focus = st.sidebar.selectbox("País (perfil horario)", countries,
                             index=countries.index(default[0]) if default else 0,
                             format_func=name)


def _norm(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)


# 1) Radar de perfil
st.subheader(f"① Perfil comparado — {year}")
st.caption("Cada eje está normalizado entre el peor (0) y el mejor (1) país del año. "
           "Más área = mejor perfil global.")
m = country_metrics_year(year).copy()
m["Renovables"] = _norm(m["renewable_share_mean"])
m["Electricidad limpia"] = 1 - _norm(m["carbon_intensity_mean"])
m["Aire limpio"] = 1 - _norm(m["pm25_mean"])
m["Asequibilidad"] = 1 - _norm(m["price_mean"])
m["Generación"] = _norm(m["total_generation_gwh"])
axes = ["Renovables", "Electricidad limpia", "Aire limpio", "Asequibilidad", "Generación"]

if not selected:
    st.info("Selecciona al menos un país en la barra lateral.")
else:
    palette = px.colors.qualitative.Bold
    fig_radar = go.Figure()
    for i, c in enumerate(selected):
        row = m[m["country"] == c]
        if row.empty:
            continue
        color = palette[i % len(palette)]
        vals = [float(row[a].iloc[0]) if pd.notna(row[a].iloc[0]) else 0 for a in axes]
        fig_radar.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=axes + [axes[0]],
            fill="toself", name=name(c), opacity=0.5,
            line=dict(color=color, width=2.5), marker=dict(color=color, size=6),
        ))
    fig_radar.update_layout(
        height=480, polar=dict(radialaxis=dict(range=[0, 1], showticklabels=True)),
        legend=dict(title=""),
    )
    st.plotly_chart(fig_radar, width="stretch", config=PLOTLY_CONFIG)

st.divider()

# 2) Treemap de generación europea
st.subheader(f"② Mezcla de generación europea — {year}")
fm = fuel_mix_year()
fm = fm[(fm["year"] == year) & (fm["gwh"] > 0)].copy()
fm["País"] = fm["country"].map(name)
fig_tree = px.treemap(
    fm, path=[px.Constant("Europa"), "País", "fuel_group"], values="gwh",
    color="fuel_group", color_discrete_map=FUEL_GROUP_COLORS,
    custom_data=["fuel_group"],
)
fig_tree.update_traces(
    hovertemplate="<b>%{label}</b><br>%{value:,.0f} GWh<br>%{percentParent:.0%} del nivel<extra></extra>",
)
fig_tree.update_layout(height=560, margin=dict(t=30, l=0, r=0, b=0))
st.plotly_chart(fig_tree, width="stretch", config=PLOTLY_CONFIG)
st.caption("Tamaño = energía generada (GWh). Haz clic en un país para ampliar su mezcla por fuente.")

st.divider()

# 3) Rango de PM2.5 dentro de cada país
st.subheader(f"③ Dispersión de PM2.5 dentro de cada país — {year}")
p = pm25()
p = p[p["year"] == year].dropna(subset=["pm25_mean"]).copy()
p["País"] = p["country"].map(name)
p = p.sort_values("pm25_mean")
if p.empty:
    st.info("Sin datos de PM2.5 para este año.")
else:
    fig_rng = go.Figure()
    # Línea mín–máx por país.
    xs, ys = [], []
    for _, r in p.iterrows():
        xs += [r["pm25_min"], r["pm25_max"], None]
        ys += [r["País"], r["País"], None]
    fig_rng.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                 line=dict(color="#ccc", width=3),
                                 name="mín–máx", hoverinfo="skip"))
    for col, color, label in [("pm25_p25", "#74add1", "P25"),
                              ("pm25_mean", "#d73027", "media"),
                              ("pm25_p75", "#f46d43", "P75")]:
        fig_rng.add_trace(go.Scatter(
            x=p[col], y=p["País"], mode="markers", name=label,
            marker=dict(size=9 if col == "pm25_mean" else 7, color=color),
            hovertemplate=f"%{{y}} · {label}: %{{x:.1f}} µg/m³<extra></extra>",
        ))
    fig_rng.add_vline(x=5, line_dash="dot", line_color="#2ecc71",
                      annotation_text="OMS 5", annotation_position="top")
    fig_rng.update_layout(height=620, xaxis_title="PM2.5 (µg/m³)",
                          legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig_rng, width="stretch", config=PLOTLY_CONFIG)
    st.caption("Cada fila muestra el rango (mín–máx), el rango intercuartílico (P25–P75) "
               "y la media de PM2.5 dentro del país: a mayor anchura, más desigualdad "
               "territorial (zonas urbanas frente a rurales).")

st.divider()

# 4) Mejor hora para consumir
st.subheader(f"④ ¿Cuándo es más limpia la electricidad? — {name(focus)}")
hp = hourly_profile()
h = hp[hp["country"] == focus].groupby("hour").agg(
    ci=("carbon_intensity_mean", "mean"),
    ren=("renewable_share_mean", "mean"),
).reindex(range(24)).reset_index()
if h["ci"].isna().all():
    st.info("Sin datos de perfil horario para este país.")
else:
    best = int(h.loc[h["ci"].idxmin(), "hour"])
    worst = int(h.loc[h["ci"].idxmax(), "hour"])
    k1, k2, k3 = st.columns(3)
    k1.metric("Hora más limpia", f"{best:02d}:00", f"{h['ci'].min():.0f} gCO₂/kWh")
    k2.metric("Hora más sucia", f"{worst:02d}:00", f"{h['ci'].max():.0f} gCO₂/kWh",
              delta_color="inverse")
    k3.metric("Renovables a la hora limpia",
              f"{h.loc[h['hour'] == best, 'ren'].iloc[0]*100:.0f} %")

    fig_clock = go.Figure(go.Barpolar(
        r=h["ci"], theta=[hh * 15 for hh in h["hour"]], width=[14] * 24,
        customdata=[f"{hh:02d}:00" for hh in h["hour"]],
        marker=dict(color=h["ci"], colorscale="RdYlGn_r",
                    colorbar=dict(title="gCO₂/kWh", thickness=12, len=0.6)),
        hovertemplate="%{customdata} h<br>%{r:.0f} gCO₂/kWh<extra></extra>",
    ))
    fig_clock.update_layout(
        height=480,
        polar=dict(
            angularaxis=dict(
                tickmode="array", tickvals=[hh * 15 for hh in range(0, 24, 3)],
                ticktext=[f"{hh:02d}h" for hh in range(0, 24, 3)],
                direction="clockwise", rotation=90,
            ),
            radialaxis=dict(showticklabels=True, ticksuffix=""),
        ),
    )
    st.plotly_chart(fig_clock, width="stretch", config=PLOTLY_CONFIG)
    st.caption("Reloj de 24 h: cada sector es una hora del día y su color/longitud la "
               "intensidad de carbono media. Las horas verdes (normalmente el mediodía "
               "solar) son las mejores para consumir electricidad.")
