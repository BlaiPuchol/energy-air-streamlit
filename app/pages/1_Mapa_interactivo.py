import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from app.components import (
    PLOTLY_CONFIG,
    name, country_year, pm25, prices_year, available_countries,
    choropleth, bivariate_choropleth, raster_overlay_map,
    country_profile, fuel_shares_for, fuel_mix_donut,
)
from src.config import PM25_YEARS

st.set_page_config(page_title="Mapa interactivo", page_icon="🗺️", layout="wide")
st.title("Mapa interactivo de Europa")

#  Definición de los parámetros visualizables 
PARAMS = {
    "Intensidad de carbono": dict(
        source="country_year", col="carbon_intensity_mean",
        unit="gCO₂/kWh", scale="YlOrRd", reverse=False,
        desc="Emisiones de CO₂ por kWh generado. Más oscuro = electricidad más sucia.",
    ),
    "Cuota renovable": dict(
        source="country_year", col="renewable_share_mean",
        unit="% renovable", scale="Greens", reverse=False,
        desc="Fracción de la generación de origen renovable. Más oscuro = más limpio.",
    ),
    "PM2.5 (calidad del aire)": dict(
        source="pm25", col="pm25_mean",
        unit="µg/m³", scale="YlOrBr", reverse=False,
        desc="Media anual de partículas finas (raster EEA 1 km). Directriz OMS: 5 µg/m³.",
    ),
    "Precio mayorista": dict(
        source="prices", col="price_mean",
        unit="€/MWh", scale="Purples", reverse=False,
        desc="Precio medio del mercado día-anterior (precios locales convertidos a EUR).",
    ),
}

# Controles

# El parámetro solo aplica a la coropleta: el mapa bivariante (PM2.5 × carbono) y
# el raster (PM2.5) tienen parámetros fijos, así que ese control solo aparece en
# el estilo «Coropleta» para que los controles sean coherentes.
st.sidebar.header("Controles del mapa")
style = st.sidebar.radio(
    "Estilo de mapa",
    ["Coropleta", "Bivariante (PM2.5 × carbono)", "Raster PM2.5 (1 km)"],
)
param, cfg = None, None
if style == "Coropleta":
    param = st.sidebar.selectbox("Parámetro a visualizar", list(PARAMS.keys()))
    cfg = PARAMS[param]
year = st.sidebar.slider("Año", min(PM25_YEARS), max(PM25_YEARS), max(PM25_YEARS))
countries = available_countries()


def _values_for(param_cfg: dict, year: int) -> pd.DataFrame:
    """Devuelve un DataFrame country + <col> para el parámetro y año dados."""
    src = param_cfg["source"]
    col = param_cfg["col"]
    if src == "country_year":
        df = country_year()
        df = df[df["year"] == year][["country", col]].copy()
        if col == "renewable_share_mean":
            df[col] = df[col] * 100
    elif src == "pm25":
        df = pm25()
        df = df[df["year"] == year][["country", col]].copy()
    else:  # prices
        df = prices_year()
        df = df[df["year"] == year][["country", col]].copy()
    return df.dropna(subset=[col])


def _clicked_country(event) -> str | None:
    """Extrae el código de país de un evento de selección de Plotly (clic en el mapa)."""
    try:
        points = event["selection"]["points"]
    except (TypeError, KeyError):
        points = []
    if points:
        p = points[0]
        loc = p.get("location")
        if loc:
            return loc
        cd = p.get("customdata")
        if cd:
            return cd[0] if isinstance(cd, (list, tuple)) else cd
    return None


#  Render según estilo

clicked = None
ranking_data = None  # se rellena en estilo Coropleta para el ranking del final

if style == "Coropleta":
    data = _values_for(cfg, year)
    if data.empty:
        st.warning(f"No hay datos de «{param}» para {year}.")
    else:
        data = data.sort_values(cfg["col"], ascending=False).reset_index(drop=True)
        data["rango"] = data.index + 1
        fig = choropleth(
            data, cfg["col"], title=f"{param} — {year}", unit=cfg["unit"],
            colorscale=cfg["scale"], reverse=cfg["reverse"],
            hover_extra={"rango": True},
        )
        st.caption("Haz clic en un país para ver su ficha detallada más abajo.")
        event = st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG,
                                key="mapa_coropleta", on_select="rerun",
                                selection_mode="points")
        clicked = _clicked_country(event)
        st.caption(f"**{param}** ({cfg['unit']}). {cfg['desc']}")
        ranking_data = data

elif style.startswith("Bivariante"):
    ci = country_year()
    ci = ci[ci["year"] == year][["country", "carbon_intensity_mean"]]
    pm = pm25()
    pm = pm[pm["year"] == year][["country", "pm25_mean"]]
    merged = ci.merge(pm, on="country", how="inner")
    if merged.empty:
        st.warning(f"No hay datos combinados PM2.5 / carbono para {year}.")
    else:
        fig = bivariate_choropleth(
            merged, pm_col="pm25_mean", ci_col="carbon_intensity_mean",
            title=f"PM2.5 × intensidad de carbono — {year}",
        )
        st.caption("Haz clic en un país para ver su ficha detallada más abajo.")
        event = st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG,
                                key="mapa_bivariante", on_select="rerun",
                                selection_mode="points")
        clicked = _clicked_country(event)
        st.caption(
            "Mapa **bivariante**: cada país se clasifica en terciles de PM2.5 y de "
            "intensidad de carbono, y el color combina ambas dimensiones según la matriz "
            "de la esquina. Las celdas **oscuras** (arriba-derecha) marcan donde coinciden "
            "**electricidad sucia y mal aire**; las **claras** (abajo-izquierda), aire "
            "limpio y electricidad baja en carbono."
        )

else:  # Raster PM2.5
    from streamlit_folium import st_folium
    st.markdown(f"#### Concentración de PM2.5 a 1 km — {year}")
    st.caption(
        "Capa raster interpolada de la EEA (resolución 1 km², EPSG:3035) superpuesta a "
        "los contornos nacionales. Haz clic en un país para ver su ficha más abajo."
    )
    m = raster_overlay_map(year)
    ev = st_folium(m, use_container_width=True, height=560, key=f"raster_{year}",
                   returned_objects=["last_active_drawing"])
    drawing = (ev or {}).get("last_active_drawing") or {}
    code = (drawing.get("properties") or {}).get("NUTS_ID")
    if code:
        clicked = code

#  Ficha del país (clic en el mapa o desplegable) 
st.divider()
st.subheader("Ficha del país")

if "mapa_sel_country" not in st.session_state:
    st.session_state.mapa_sel_country = "ES" if "ES" in countries else countries[0]
# Un clic en el mapa actualiza el país seleccionado (antes de crear el widget).
if clicked and clicked in countries:
    st.session_state.mapa_sel_country = clicked

csel, _ = st.columns([1, 3])
with csel:
    detail = st.selectbox("País (o haz clic en el mapa)", countries,
                          key="mapa_sel_country", format_func=name)

prof = country_profile(detail, year)


def _fmt(key, suffix, factor=1.0, dec=0):
    v = prof.get(key)
    return f"{v * factor:.{dec}f}{suffix}" if v is not None else "N/D"


st.markdown(f"### {name(detail)} — {year}")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Generación total", _fmt("generation_gwh", " GWh"))
m2.metric("Intensidad de carbono", _fmt("carbon_intensity", " gCO₂/kWh"))
m3.metric("Cuota renovable", _fmt("renewable_share", " %", 100))
m4.metric("PM2.5 media", _fmt("pm25", " µg/m³", dec=1),
          help="Directriz OMS anual de referencia: 5 µg/m³.")
m5.metric("Precio medio", _fmt("price", " €/MWh"))

shares = fuel_shares_for(detail, year)
if shares:
    st.plotly_chart(
        fuel_mix_donut(shares, title=f"Mezcla de generación — {name(detail)} ({year})"),
        width="stretch", config=PLOTLY_CONFIG,
    )
else:
    st.info("Sin datos de mezcla de generación para este país y año.")

#  Ranking (5 más altos / más bajos) al final de la página 
if ranking_data is not None:
    st.divider()
    st.subheader(f"Ranking — {param} ({year})")
    cR1, cR2 = st.columns(2)
    with cR1:
        st.markdown("**5 valores más altos**")
        top = ranking_data.head(5).copy()
        top["pais"] = top["country"].map(name)
        st.dataframe(
            top[["rango", "pais", cfg["col"]]].rename(
                columns={"pais": "País", cfg["col"]: cfg["unit"]}),
            hide_index=True, width="stretch",
        )
    with cR2:
        st.markdown("**5 valores más bajos**")
        bot = ranking_data.tail(5).iloc[::-1].copy()
        bot["pais"] = bot["country"].map(name)
        st.dataframe(
            bot[["rango", "pais", cfg["col"]]].rename(
                columns={"pais": "País", cfg["col"]: cfg["unit"]}),
            hide_index=True, width="stretch",
        )
