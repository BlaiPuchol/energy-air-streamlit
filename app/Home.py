import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from app.components import (
    PLOTLY_CONFIG,
    name, country_year, fuel_mix_year, live_generation, fuel_mix_donut,
    available_countries,
)
from src.config import FUEL_GROUPS

st.set_page_config(
    page_title="Energía y aire en Europa",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Energía y calidad del aire en Europa")
st.markdown(
    "#### Dónde las decisiones energéticas de Europa se convierten en el aire que respira"
)

st.markdown(
    """
Esta aplicación cruza **datos históricos** (26 países, 2019–2024) con **datos en tiempo real**
para explorar la relación entre cómo se produce la electricidad y la calidad del aire.

**Datos históricos** (descargados y preagregados; la web los lee de ficheros, sin llamar a APIs):

- **Generación eléctrica horaria** por tipo de fuente y **precios** día-anterior — *ENTSO-E Transparency Platform*
- **PM2.5** interpolada a 1 km e **inventario sectorial de emisiones** — *Agencia Europea de Medio Ambiente (EEA)*
- **Contornos administrativos NUTS-0** — *Eurostat GISCO*

**Datos en tiempo real** (APIs consultadas en el momento):

- **Generación e intensidad de carbono** ahora mismo — *Energy-Charts / Fraunhofer ISE* (sin clave; ENTSO-E de respaldo)
- **PM2.5 medida en estaciones** — *OpenAQ*
"""
)

# Tarjetas de navegación
st.markdown("### Explora")
c1, c2, c3, c4, c5 = st.columns(5)
c1.info("**Mapa interactivo**\n\nCoropletas de intensidad de carbono, renovables, PM2.5 y precios, con selector de parámetro, año y estilo.")
c2.success("**Evolución**\n\nSeries temporales, trayectoria animada, mapa por año y mapa de calor hora×mes.")
c3.warning("**Fuentes y emisiones**\n\n¿Qué sector ensucia el aire? Atribución sectorial EEA, descarbonización e histórico.")
c4.error("**Comparativa**\n\nRadar de perfiles, treemap de generación, dispersión de PM2.5 y mejor hora para consumir.")
c5.info("**Tiempo real**\n\nMezcla eléctrica en vivo, intensidad de carbono y calidad del aire de las últimas horas.")

st.divider()

# Instantánea en vivo
st.subheader("Ahora mismo en Europa")

default_country = "ES" if "ES" in available_countries() else available_countries()[0]
RANGES = {"Últimas 24 h": 1, "Última semana": 7, "Último mes": 30}
colsel, colrange, _ = st.columns([1, 1, 2])
with colsel:
    snap_country = st.selectbox(
        "País para la instantánea en vivo",
        available_countries(),
        index=available_countries().index(default_country),
        format_func=name,
    )
with colrange:
    range_label = st.selectbox("Periodo", list(RANGES.keys()))
days = RANGES[range_label]
period_txt = range_label.lower()

with st.spinner(f"Consultando generación en vivo de {name(snap_country)} ({period_txt})…"):
    live_df, source = live_generation(snap_country, days=days)

if live_df.empty:
    st.info(
        "No se ha podido obtener generación en vivo en este momento. "
        "La sección **Tiempo real** ofrece más detalle y respaldo histórico."
    )
else:
    # Mezcla por grupo de combustible (media del periodo seleccionado, MW).
    shares = {}
    for group, cols in FUEL_GROUPS.items():
        present = [c for c in cols if c in live_df.columns]
        if present:
            shares[group] = float(live_df[present].clip(lower=0).mean().sum())

    ci_now = live_df["carbon_intensity_gco2_kwh"].dropna()
    ren_now = live_df["renewable_share"].dropna()
    gen_now = live_df["total_generation_mw"].dropna()
    ts = live_df.index.max()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Intensidad de carbono", f"{ci_now.iloc[-1]:.0f} gCO₂/kWh" if len(ci_now) else "N/D")
    k2.metric("Cuota renovable", f"{ren_now.iloc[-1]*100:.0f} %" if len(ren_now) else "N/D")
    k3.metric("Generación total", f"{gen_now.iloc[-1]/1000:.1f} GW" if len(gen_now) else "N/D")
    k4.metric("Fuente", "En vivo" if source else "Histórico")

    colA, colB = st.columns([1, 1])
    with colA:
        st.plotly_chart(
            fuel_mix_donut(shares, title=f"Mezcla eléctrica ({period_txt}) — {name(snap_country)}"),
            width="stretch", config=PLOTLY_CONFIG,
        )
    with colB:
        st.markdown(f"**{range_label}** · datos hasta `{ts:%Y-%m-%d %H:%M}`")
        st.caption(
            "Intensidad de carbono = emisiones (gCO₂) / energía generada (kWh), "
            "usando factores de emisión por tipo de fuente (IPCC AR6). "
            "La evolución detallada y el mapa europeo en vivo están en la página **Tiempo real**."
        )

st.divider()

# Contexto histórico rápido
st.subheader("Para situarse: los extremos de 2024")
cy = country_year()
latest = int(cy["year"].max())
cyl = cy[cy["year"] == latest].dropna(subset=["carbon_intensity_mean"])
if not cyl.empty:
    cleanest = cyl.nsmallest(1, "carbon_intensity_mean").iloc[0]
    dirtiest = cyl.nlargest(1, "carbon_intensity_mean").iloc[0]
    greenest = cyl.nlargest(1, "renewable_share_mean").iloc[0]
    g1, g2, g3 = st.columns(3)
    g1.metric(f"Más limpio ({latest})", name(cleanest["country"]),
              f"{cleanest['carbon_intensity_mean']:.0f} gCO₂/kWh")
    g2.metric(f"Más intensivo ({latest})", name(dirtiest["country"]),
              f"{dirtiest['carbon_intensity_mean']:.0f} gCO₂/kWh")
    g3.metric(f"Más renovable ({latest})", name(greenest["country"]),
              f"{greenest['renewable_share_mean']*100:.0f} %")

st.caption(
    "Proyecto de la asignatura *Visualización de Datos* — MIARFID, Universitat Politècnica "
    "de València. Autor: Blai Puchol Salort. Datos: ENTSO-E, EEA, Eurostat GISCO, "
    "Energy-Charts (Fraunhofer) y OpenAQ."
)
