import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from src.config import (
    COUNTRY_NAMES, FUEL_GROUPS, FUEL_GROUP_COLORS, EMISSION_FACTORS,
    RENEWABLE_TYPES, EEA_SECTORS, PM25_YEARS, DATA_APP,
)
from src.data_loaders import (
    load_app_country_year, load_app_country_month,
    load_app_fuel_mix_year, load_app_fuel_mix_month,
    load_app_hourly_profile, load_app_prices_year, load_app_prices_month,
    load_app_pm25, load_app_emissions, load_app_geojson,
    load_generation_live_fraunhofer, load_generation_live,
    fetch_openaq_pm25_latest,
)
from src.processing import compute_carbon_intensity


def _secret(key_name: str) -> str:
    """Lee una clave de st.secrets (Streamlit Cloud) o de las variables de entorno."""
    try:
        val = st.secrets.get(key_name, "")
    except Exception:
        val = ""
    return val or os.getenv(key_name, "")

MONTH_NAMES_ES = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]

# Configuración común de Plotly: locale español (meses/días en español y hora en
# formato 24 h) y sin el logo de Plotly. Pasar a todos los st.plotly_chart.
PLOTLY_CONFIG = {"locale": "es", "displaylogo": False}


def name(code: str) -> str:
    """Código ISO → nombre del país en español."""
    return COUNTRY_NAMES.get(code, code)


# Cargadores cacheados

@st.cache_data
def country_year() -> pd.DataFrame:
    return load_app_country_year()


@st.cache_data
def country_month() -> pd.DataFrame:
    df = load_app_country_month()
    df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
    return df


@st.cache_data
def fuel_mix_year() -> pd.DataFrame:
    return load_app_fuel_mix_year()


@st.cache_data
def fuel_mix_month() -> pd.DataFrame:
    df = load_app_fuel_mix_month()
    df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
    return df


@st.cache_data
def hourly_profile() -> pd.DataFrame:
    return load_app_hourly_profile()


@st.cache_data
def prices_year() -> pd.DataFrame:
    return load_app_prices_year()


@st.cache_data
def prices_month() -> pd.DataFrame:
    df = load_app_prices_month()
    df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
    return df


@st.cache_data
def pm25() -> pd.DataFrame:
    return load_app_pm25()


@st.cache_data
def emissions() -> pd.DataFrame:
    return load_app_emissions()


@st.cache_resource
def geojson() -> dict:
    return load_app_geojson()


@st.cache_data
def country_centroids() -> dict:
    """Centro aproximado (lat, lon) de cada país.

    Usa la mediana de los vértices (robusta frente a islas/territorios lejanos como
    Canarias o el norte de Noruega, que descentran el recuadro de la geometría).
    """
    import statistics
    gj = geojson()
    out = {}
    for feat in gj["features"]:
        code = feat["properties"]["NUTS_ID"]
        lats, lons = [], []

        def _collect(coords):
            if coords and isinstance(coords[0], (int, float)):
                lons.append(coords[0])
                lats.append(coords[1])
            else:
                for c in coords:
                    _collect(c)

        _collect(feat["geometry"]["coordinates"])
        if lats and lons:
            out[code] = (statistics.median(lats), statistics.median(lons))
    return out


@st.cache_data
def available_countries() -> list:
    """Países presentes en los datos de generación, ordenados por nombre."""
    cy = country_year()
    return sorted(cy["country"].unique(), key=lambda c: name(c))


@st.cache_data
def country_metrics_year(year: int) -> pd.DataFrame:
    """Une por país (un año) intensidad de carbono, renovables, generación, PM2.5 y precio."""
    cy = country_year()
    cy = cy[cy["year"] == year][
        ["country", "carbon_intensity_mean", "renewable_share_mean", "total_generation_gwh"]
    ]
    pm = pm25()
    pm = pm[pm["year"] == year][["country", "pm25_mean"]]
    pr = prices_year()
    pr = pr[pr["year"] == year][["country", "price_mean"]]
    return cy.merge(pm, on="country", how="left").merge(pr, on="country", how="left")


@st.cache_data
def country_profile(code: str, year: int) -> dict:
    """Ficha de un país para un año: intensidad de carbono, renovables, PM2.5, precio, generación."""
    out = {"country": code, "name": name(code), "year": year}
    cy = country_year()
    row = cy[(cy["country"] == code) & (cy["year"] == year)]
    if not row.empty:
        out["carbon_intensity"] = float(row["carbon_intensity_mean"].iloc[0])
        out["renewable_share"] = float(row["renewable_share_mean"].iloc[0])
        out["generation_gwh"] = float(row["total_generation_gwh"].iloc[0])
    pm = pm25()
    pmr = pm[(pm["country"] == code) & (pm["year"] == year)]
    if not pmr.empty:
        out["pm25"] = float(pmr["pm25_mean"].iloc[0])
    pr = prices_year()
    prr = pr[(pr["country"] == code) & (pr["year"] == year)]
    if not prr.empty:
        out["price"] = float(prr["price_mean"].iloc[0])
    return out


@st.cache_data
def fuel_shares_for(code: str, year: int) -> dict:
    """Mezcla de generación {grupo: GWh} de un país y año (para el donut de detalle)."""
    fm = fuel_mix_year()
    sub = fm[(fm["country"] == code) & (fm["year"] == year)]
    return {r["fuel_group"]: float(r["gwh"]) for _, r in sub.iterrows() if r["gwh"] > 0}


# Mapas

def _add_names(df: pd.DataFrame, code_col: str = "country") -> pd.DataFrame:
    df = df.copy()
    df["pais"] = df[code_col].map(name)
    return df


# Mapas de teselas (MapLibre): ocupan todo el ancho como el mapa raster (Leaflet)
# y usan la proyección web-Mercator, familiar y sin la distorsión de equirectangular.
MAP_STYLE = "carto-positron"
EUROPE_CENTER = {"lat": 55.0, "lon": 13.0}
EUROPE_ZOOM = 3.1


def fit_europe_map(fig: go.Figure, *, height: int = 540, title: str = None) -> go.Figure:
    """Centra un mapa de teselas en Europa y lo ajusta para ocupar todo el ancho."""
    fig.update_layout(
        map_style=MAP_STYLE,
        map=dict(center=EUROPE_CENTER, zoom=EUROPE_ZOOM),
        margin=dict(l=0, r=0, t=50 if title else 8, b=0),
        height=height,
    )
    if title:
        fig.update_layout(title=dict(text=title, x=0.01, font=dict(size=18)))
    return fig


def choropleth(df: pd.DataFrame, value_col: str, *, title: str, unit: str,
               colorscale: str = "YlOrRd", reverse: bool = False,
               code_col: str = "country", hover_extra: dict = None,
               height: int = 540) -> go.Figure:
    """Coropleta NUMÉRICA sobre los contornos NUTS-0 simplificados (plotly).

    `hover_extra` permite añadir columnas adicionales al tooltip.
    """
    gj = geojson()
    d = _add_names(df, code_col)
    d = d.dropna(subset=[value_col])

    hover_data = {value_col: ":.1f", code_col: False, "pais": False}
    if hover_extra:
        hover_data.update(hover_extra)

    fig = px.choropleth_map(
        d, geojson=gj, locations=code_col, featureidkey="properties.NUTS_ID",
        color=value_col, color_continuous_scale=colorscale,
        hover_name="pais", hover_data=hover_data, custom_data=[code_col],
        labels={value_col: unit}, opacity=0.78,
        center=EUROPE_CENTER, zoom=EUROPE_ZOOM, map_style=MAP_STYLE,
    )
    if reverse:
        fig.update_coloraxes(reversescale=True)
    fit_europe_map(fig, height=height, title=title)
    fig.update_layout(coloraxis_colorbar=dict(title=unit, thickness=14, len=0.7))
    return fig


def categorical_choropleth(df: pd.DataFrame, cat_col: str, *, title: str,
                           color_map: dict, code_col: str = "country",
                           hover_extra: dict = None, height: int = 540) -> go.Figure:
    """Coropleta CATEGÓRICA (p. ej. sector dominante de emisión)."""
    gj = geojson()
    d = _add_names(df, code_col)
    hover_data = {code_col: False, "pais": False}
    if hover_extra:
        hover_data.update(hover_extra)

    fig = px.choropleth_map(
        d, geojson=gj, locations=code_col, featureidkey="properties.NUTS_ID",
        color=cat_col, color_discrete_map=color_map,
        hover_name="pais", hover_data=hover_data, custom_data=[code_col],
        category_orders={cat_col: list(color_map.keys())}, opacity=0.78,
        center=EUROPE_CENTER, zoom=EUROPE_ZOOM, map_style=MAP_STYLE,
    )
    fit_europe_map(fig, height=height, title=title)
    fig.update_layout(legend=dict(title="", orientation="h", y=-0.02))
    return fig


# Paleta bivariante 3×3 (PM2.5 en filas, intensidad de carbono en columnas).
BIVARIATE_COLORS = {
    "1-1": "#e8e8e8", "1-2": "#b8d6be", "1-3": "#73ae80",
    "2-1": "#e4acac", "2-2": "#ad9ea5", "2-3": "#6c83b5",
    "3-1": "#c85a5a", "3-2": "#985356", "3-3": "#574249",
}
BIVARIATE_LABELS = {
    "1-1": "PM2.5 baja · CI baja", "1-2": "PM2.5 baja · CI media", "1-3": "PM2.5 baja · CI alta",
    "2-1": "PM2.5 media · CI baja", "2-2": "PM2.5 media · CI media", "2-3": "PM2.5 media · CI alta",
    "3-1": "PM2.5 alta · CI baja", "3-2": "PM2.5 alta · CI media", "3-3": "PM2.5 alta · CI alta",
}


def bivariate_choropleth(df: pd.DataFrame, *, pm_col: str, ci_col: str,
                         title: str, height: int = 540) -> go.Figure:
    """Coropleta bivariante: cruza PM2.5 (calidad del aire) e intensidad de carbono."""
    d = df.dropna(subset=[pm_col, ci_col]).copy()
    if d.empty:
        return go.Figure()

    def tercile(s: pd.Series) -> pd.Series:
        try:
            return pd.qcut(s, 3, labels=[1, 2, 3]).astype(int)
        except ValueError:
            return pd.cut(s, 3, labels=[1, 2, 3]).astype(int)

    d["_pm"] = tercile(d[pm_col])
    d["_ci"] = tercile(d[ci_col])
    d["clase"] = d["_pm"].astype(str) + "-" + d["_ci"].astype(str)
    d["categoria"] = d["clase"].map(BIVARIATE_LABELS)
    color_map = {BIVARIATE_LABELS[k]: v for k, v in BIVARIATE_COLORS.items()}

    fig = categorical_choropleth(
        d, "categoria", title=title, color_map=color_map,
        hover_extra={pm_col: ":.1f", ci_col: ":.0f"}, height=height,
    )
    # Leyenda como matriz 3×3 incrustada en la esquina del mapa (como en los HTML).
    fig.update_layout(showlegend=False, images=[dict(
        source=_bivariate_legend_datauri(),
        xref="paper", yref="paper", x=0.01, y=0.99,
        sizex=0.34, sizey=0.34, xanchor="left", yanchor="top",
        sizing="contain", layer="above",
    )])
    return fig


@st.cache_data(show_spinner=False)
def _bivariate_legend_datauri() -> str:
    """Genera (una vez) la matriz 3×3 de leyenda bivariante como PNG en base64."""
    import base64
    import io
    import math
    from PIL import Image, ImageDraw, ImageFont

    def arrow(draw, x0, y0, x1, y1, color="#555", w=2, head=5):
        draw.line([(x0, y0), (x1, y1)], fill=color, width=w)
        ang = math.atan2(y1 - y0, x1 - x0)
        draw.polygon([
            (x1, y1),
            (x1 - head * math.cos(ang - 0.5), y1 - head * math.sin(ang - 0.5)),
            (x1 - head * math.cos(ang + 0.5), y1 - head * math.sin(ang + 0.5)),
        ], fill=color)

    cell, top, left, rpad, bpad = 44, 6, 48, 10, 42
    grid = cell * 3
    W, H = left + grid + rpad, top + grid + bpad
    img = Image.new("RGBA", (W, H), (255, 255, 255, 235))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=13)
    except TypeError:
        font = ImageFont.load_default()

    for ri in range(3):          # fila 0 = arriba = PM2.5 alta
        pm = 3 - ri
        for ci_i in range(3):    # col 0 = izquierda = carbono bajo
            ci = ci_i + 1
            x0, y0 = left + ci_i * cell, top + ri * cell
            draw.rectangle([x0, y0, x0 + cell, y0 + cell],
                           fill=BIVARIATE_COLORS[f"{pm}-{ci}"],
                           outline="white", width=2)

    # Eje Y (PM2.5): flecha hacia arriba + etiqueta rotada.
    arrow(draw, left - 12, top + grid, left - 12, top)
    ylab = Image.new("RGBA", (grid, 16), (0, 0, 0, 0))
    ImageDraw.Draw(ylab).text((grid / 2, 8), "PM2.5", fill="#333", font=font, anchor="mm")
    img.alpha_composite(ylab.rotate(90, expand=True), (2, top))

    # Eje X (carbono): flecha hacia la derecha + etiqueta.
    ax_y = top + grid + 12
    arrow(draw, left, ax_y, left + grid, ax_y)
    draw.text((left + grid / 2, top + grid + 20), "Carbono",
              fill="#333", font=font, anchor="ma")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def raster_overlay_map(year: int, height: int = 560):
    """Mapa Folium con la capa raster PM2.5 de 1 km superpuesta a los contornos."""
    import folium
    from folium.raster_layers import ImageOverlay

    m = folium.Map(location=[54, 13], zoom_start=4, tiles="CartoDB positron")

    png = DATA_APP / f"pm25_raster_preview_{year}.png"
    bounds_txt = DATA_APP / f"pm25_raster_bounds_{year}.txt"
    if png.exists() and bounds_txt.exists():
        import ast
        bounds = ast.literal_eval(bounds_txt.read_text().strip())
        ImageOverlay(
            image=str(png), bounds=bounds, opacity=0.75,
            name=f"PM2.5 (raster 1 km, {year})",
        ).add_to(m)

    folium.GeoJson(
        geojson(), name="Países",
        style_function=lambda x: {"fillOpacity": 0, "color": "#333", "weight": 0.7},
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["País"]),
    ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # Barra de color real (igual que el raster: YlOrRd, 0–30 µg/m³).
    gradient = ("linear-gradient(to right,#ffffcc,#ffeda0,#fed976,#feb24c,"
                "#fd8d3c,#fc4e2a,#e31a1c,#bd0026,#800026)")
    legend = (
        "<div style='position:fixed;bottom:24px;left:24px;z-index:9999;background:white;"
        "padding:10px 12px;border-radius:6px;font-size:12px;box-shadow:0 1px 4px rgba(0,0,0,.3)'>"
        f"<b>PM2.5 media anual {year}</b><br>"
        "<span style='color:#555'>Raster interpolado EEA (1 km²), µg/m³</span>"
        f"<div style='height:12px;width:200px;margin:6px 0 2px;border:1px solid #ccc;"
        f"background:{gradient}'></div>"
        "<div style='display:flex;justify-content:space-between;width:200px;color:#555'>"
        "<span>0</span><span>10</span><span>20</span><span>30+</span></div>"
        "</div>"
    )
    m.get_root().html.add_child(folium.Element(legend))
    return m


# Mezcla de generación (formato ancho para gráficos apilados)

def fuel_mix_wide(df_long: pd.DataFrame, index_cols: list) -> pd.DataFrame:
    """Pivota la mezcla de combustible de formato largo a ancho (una col por grupo)."""
    wide = df_long.pivot_table(
        index=index_cols, columns="fuel_group", values="gwh", aggfunc="sum",
    ).reset_index()
    wide.columns.name = None
    for g in FUEL_GROUPS:
        if g not in wide.columns:
            wide[g] = 0.0
    return wide


def fuel_mix_donut(shares: dict, *, title: str, height: int = 360) -> go.Figure:
    """Donut de la mezcla de generación a partir de {grupo: GWh|MW}."""
    labels = [g for g in FUEL_GROUPS if shares.get(g, 0) > 0]
    values = [shares[g] for g in labels]
    colors = [FUEL_GROUP_COLORS[g] for g in labels]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.55, marker_colors=colors,
        textinfo="label+percent", textposition="outside", automargin=True,
        hovertemplate="%{label}: %{value:.0f} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=15)),
        showlegend=False, height=height, margin=dict(l=40, r=40, t=55, b=40),
    )
    return fig


# Tiempo real─

# Energy-Charts (Fraunhofer) nombra los tipos de producción distinto a ENTSO-E.
# Mapeamos a las claves de EMISSION_FACTORS para poder calcular intensidad de carbono.
FRAUNHOFER_TO_CANONICAL = {
    "hydro pumped storage": "Hydro Pumped Storage",
    "hydro run-of-river": "Hydro Run-of-river and poundage",
    "hydro water reservoir": "Hydro Water Reservoir",
    "biomass": "Biomass",
    "fossil brown coal / lignite": "Fossil Brown coal/Lignite",
    "fossil hard coal": "Fossil Hard coal",
    "fossil coal-derived gas": "Fossil Coal-derived gas",
    "fossil oil": "Fossil Oil",
    "fossil oil shale": "Fossil Oil shale",
    "fossil peat": "Fossil Peat",
    "fossil gas": "Fossil Gas",
    "geothermal": "Geothermal",
    "nuclear": "Nuclear",
    "waste": "Waste",
    "wind offshore": "Wind Offshore",
    "wind onshore": "Wind Onshore",
    "solar": "Solar",
    "marine": "Marine",
    "others": "Other",
    "other": "Other",
    "renewable": "Other renewable",
}
# Series que NO son generación (cargas, comercio, cuotas) — se descartan.
_FRAUNHOFER_EXCLUDE_SUBSTR = (
    "load", "cross border", "share of generation", "consumption",
    "import", "export", "residual",
)


def _normalize_live(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas de Energy-Charts a las canónicas y descarta no-generación."""
    if df.empty:
        return df
    rename = {}
    drop = []
    for col in df.columns:
        low = str(col).strip().lower()
        if any(s in low for s in _FRAUNHOFER_EXCLUDE_SUBSTR):
            drop.append(col)
            continue
        canon = FRAUNHOFER_TO_CANONICAL.get(low)
        if canon:
            rename[col] = canon
        else:
            drop.append(col)
    out = df.drop(columns=drop, errors="ignore").rename(columns=rename)
    # Si varias columnas mapean al mismo nombre canónico, súmalas.
    if out.columns.duplicated().any():
        out = out.T.groupby(level=0).sum().T
    return out


@st.cache_data(ttl=900, show_spinner=False)
def live_generation(country: str, days: int = 1) -> tuple:
    """Generación de los últimos `days` días con intensidad de carbono.

    Devuelve (df_canónico_con_CI, fuente) donde fuente ∈ {'fraunhofer','entsoe',None}.
    """
    raw = load_generation_live_fraunhofer(country, days=days)
    source = "fraunhofer"
    if raw.empty:
        try:
            from entsoe import EntsoePandasClient
            key = _secret("ENTSOE_API_KEY")
            if key:
                client = EntsoePandasClient(api_key=key)
                raw = load_generation_live(client, country, days=days)
                source = "entsoe"
        except Exception:
            raw = pd.DataFrame()

    if raw.empty:
        return pd.DataFrame(), None

    if source == "fraunhofer":
        raw = _normalize_live(raw)
    df = compute_carbon_intensity(raw)
    return df, source


@st.cache_data(ttl=900, show_spinner=True)
def live_carbon_all(countries: list) -> pd.DataFrame:
    """Intensidad de carbono media (24 h) por país en vivo; respaldo histórico si falla."""
    cy = country_year()
    latest_year = int(cy["year"].max())
    fallback = cy[cy["year"] == latest_year].set_index("country")

    records = []
    for c in countries:
        df, source = live_generation(c)
        if not df.empty and df["carbon_intensity_gco2_kwh"].notna().any():
            records.append({
                "country": c,
                "carbon_intensity_mean": df["carbon_intensity_gco2_kwh"].mean(),
                "renewable_share_mean": df["renewable_share"].mean(),
                "source": source,
            })
        elif c in fallback.index:
            records.append({
                "country": c,
                "carbon_intensity_mean": fallback.loc[c, "carbon_intensity_mean"],
                "renewable_share_mean": fallback.loc[c, "renewable_share_mean"],
                "source": "historical",
            })
    return pd.DataFrame(records)


@st.cache_data(ttl=900, show_spinner=False)
def live_pm25_europe(hours: int = 3, max_pages: int = 12) -> pd.DataFrame:
    """PM2.5 medida en tiempo real en estaciones europeas (OpenAQ v3)."""
    return fetch_openaq_pm25_latest(_secret("OPENAQ_API_KEY"),
                                    hours=hours, max_pages=max_pages)


def openaq_available() -> bool:
    return bool(_secret("OPENAQ_API_KEY"))


# Niveles de calidad del aire por PM2.5 (referencias OMS 2021), de mejor a peor.
PM25_QUALITY_LEVELS = ["Buena", "Aceptable", "Moderada", "Mala", "Muy mala"]


def pm25_quality(v: float) -> str:
    """Calidad del aire según la PM2.5 (referencias OMS 2021). Más PM2.5 = peor calidad."""
    if v <= 5:
        return "Buena"
    if v <= 15:
        return "Aceptable"
    if v <= 25:
        return "Moderada"
    if v <= 50:
        return "Mala"
    return "Muy mala"


# Colores anclados a umbrales de PM2.5 (µg/m³): verde → amarillo → naranja → rojo
# → violeta → casi negro para el aire muy contaminado.
PM25_COLOR_ANCHORS = [
    (0,   "#1a9850"),  # verde
    (5,   "#a6d96a"),  # verde claro (OMS anual)
    (15,  "#fee08b"),  # amarillo (OMS 24 h)
    (25,  "#fdae61"),  # naranja
    (50,  "#d73027"),  # rojo
    (75,  "#7b3294"),  # violeta
    (100, "#2d0033"),  # violeta muy oscuro / casi negro
]


def _pm25_colorscale(vmax: float):
    """Escala de color (lista [pos, color]) con paradas en los umbrales reales/vmax."""
    scale, last = [], -1.0
    for val, color in PM25_COLOR_ANCHORS:
        pos = min(val / vmax, 1.0)
        if pos <= last:
            continue
        scale.append([pos, color])
        last = pos
    scale[0][0] = 0.0
    scale[-1][0] = 1.0
    return scale


def pm25_points_map(df: pd.DataFrame, *, height: int = 560,
                    vmax: float = None) -> go.Figure:
    """Mapa de puntos con la PM2.5 más reciente por estación (OpenAQ).

    Color continuo verde→rojo por concentración de PM2.5 (verde = aire limpio). `vmax`
    fija el máximo de la escala; si es None, se toma el máximo real de los datos.
    """
    d = df.dropna(subset=["lat", "lon", "pm25"]).copy()
    if d.empty:
        return go.Figure()

    d["hora"] = pd.to_datetime(d["datetime"], errors="coerce", utc=True).dt.strftime("%d/%m %H:%M UTC")
    d["hora"] = d["hora"].fillna("—")
    d["calidad"] = d["pm25"].apply(pm25_quality)
    d["estacion"] = "Estación OpenAQ " + d["location_id"].astype("Int64").astype(str)
    d["coord"] = d["lat"].round(3).astype(str) + ", " + d["lon"].round(3).astype(str)

    if vmax is None:
        import math
        vmax = min(100.0, max(25.0, math.ceil(float(d["pm25"].max()) / 5) * 5))
    fig = px.scatter_map(
        d, lat="lat", lon="lon", color="pm25",
        color_continuous_scale=_pm25_colorscale(vmax), range_color=(0, vmax),
        custom_data=["estacion", "pm25", "calidad", "hora", "coord"],
        center=EUROPE_CENTER, zoom=EUROPE_ZOOM, map_style=MAP_STYLE,
    )
    fig.update_traces(
        marker=dict(size=8, opacity=0.85),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "PM2.5: <b>%{customdata[1]:.1f} µg/m³</b><br>"
            "Calidad del aire: %{customdata[2]}<br>"
            "Última medición: %{customdata[3]}<br>"
            "Coordenadas: %{customdata[4]}"
            "<extra></extra>"
        ),
    )
    ticks = [t for t in (0, 5, 15, 25, 50, 75, 100) if t <= vmax]
    if ticks[-1] != vmax:
        ticks.append(vmax)
    fit_europe_map(fig, height=height)
    fig.update_layout(
        coloraxis_colorbar=dict(title="PM2.5<br>µg/m³", thickness=14, len=0.7,
                                tickvals=ticks),
    )
    return fig


def carbon_gauge(value: float, *, title: str = "Intensidad de carbono (gCO₂/kWh)",
                 height: int = 300) -> go.Figure:
    """Indicador tipo aguja para la intensidad de carbono en vivo."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(value),
        number={"suffix": " gCO₂/kWh", "font": {"size": 28}},
        title={"text": title, "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 800]},
            "bar": {"color": "#2c3e50"},
            "steps": [
                {"range": [0, 100], "color": "#1a9850"},
                {"range": [100, 250], "color": "#a6d96a"},
                {"range": [250, 450], "color": "#fee08b"},
                {"range": [450, 650], "color": "#fc8d59"},
                {"range": [650, 800], "color": "#d73027"},
            ],
        },
    ))
    fig.update_layout(height=height, margin=dict(l=20, r=20, t=50, b=10))
    return fig
