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
    name, country_year, pm25, emissions, categorical_choropleth,
    available_countries,
)
from src.processing import rank_dominant_sector, compute_decoupling_rate
from src.config import EEA_SECTORS, PM25_YEARS

st.set_page_config(page_title="Fuentes y emisiones", page_icon="🏭", layout="wide")
st.title("Fuentes y emisiones: ¿por qué el aire es como es?")

SECTOR_COLORS = {
    "Electricidad y calor": "#34495e",
    "Transporte por carretera": "#e67e22",
    "Calefacción residencial": "#27ae60",
    "Industria": "#7f8c8d",
    "Agricultura": "#f1c40f",
}

# Controles─
countries = available_countries()
st.sidebar.header("Controles")
pollutant = st.sidebar.selectbox("Contaminante", ["PM2.5", "NOx", "NH3", "SO2"])
eea_year = st.sidebar.slider("Año del inventario EEA", 2000, 2023, 2022)
default = [c for c in ["DE", "FR", "PL", "ES", "IT", "NL"] if c in countries]
selected = st.sidebar.multiselect(
    "Países (gráficas)", countries, default=default, format_func=name)

eea = emissions()
POLLUTANTS = ["PM2.5", "NOx", "NH3", "SO2"]


def _clicked_country(event):
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


# 1) Mapa de sector dominante
st.subheader(f"① Sector que más {pollutant} emite por país ({eea_year})")
dominant = rank_dominant_sector(eea, pollutant=pollutant, year=eea_year)
clicked = None
if dominant.empty:
    st.warning(f"No hay datos de {pollutant} para {eea_year}.")
else:
    dominant = dominant.rename(columns={"country_code": "country"})
    colm, cold = st.columns([2, 1])
    with colm:
        fig1 = categorical_choropleth(
            dominant, "sector_name",
            title=f"Sector dominante de {pollutant} — {eea_year}",
            color_map=SECTOR_COLORS,
            hover_extra={"emissions_tonnes": ":,.0f"},
        )
        st.caption("Haz clic en un país para ver su detalle debajo.")
        ev = st.plotly_chart(fig1, width="stretch", config=PLOTLY_CONFIG,
                             key="dom_map", on_select="rerun", selection_mode="points")
        clicked = _clicked_country(ev)
    with cold:
        sector_defs = {
            "Electricidad y calor": "centrales eléctricas y producción de calor.",
            "Transporte por carretera": "turismos, camiones y autobuses.",
            "Calefacción residencial": "calefacción de viviendas (p. ej. estufas de leña o calderas).",
            "Industria": "combustión y procesos industriales.",
            "Agricultura": "ganadería y fertilizantes (sobre todo amoníaco).",
        }
        items = "".join(
            f'<li style="margin-bottom:4px">'
            f'<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
            f'background:{SECTOR_COLORS[s]};margin-right:7px;vertical-align:middle"></span>'
            f"<b>{s}</b> — {d}</li>"
            for s, d in sector_defs.items()
        )
        st.markdown(f"**Cómo leer el mapa**")
        st.markdown(
            f"Cada país se colorea según el sector que más toneladas de {pollutant} "
            f"emite. Los sectores (clasificación NFR de la EEA) son:"
        )
        st.markdown(f'<ul style="padding-left:18px">{items}</ul>', unsafe_allow_html=True)
        st.caption(
            "El sector dominante en cada país depende del contaminante y del año seleccionados."
        )

# Detalle del país (clic en el mapa o desplegable)
st.markdown("**Detalle del país**")
if "fuentes_detail" not in st.session_state:
    st.session_state.fuentes_detail = selected[0] if selected else countries[0]
if clicked and clicked in countries:
    st.session_state.fuentes_detail = clicked
dsel, _ = st.columns([1, 3])
with dsel:
    detail = st.selectbox("País (o haz clic en el mapa)", countries,
                          key="fuentes_detail", format_func=name)

dsub = eea[(eea["country_code"] == detail) & (eea["pollutant"] == pollutant) &
           (eea["sector_code"].isin(EEA_SECTORS))].copy()
dsub["sector_name"] = dsub["sector_code"].map(EEA_SECTORS)
dc1, dc2 = st.columns(2)
with dc1:
    comp = dsub[dsub["year"] == eea_year].groupby("sector_name")["emissions_tonnes"].sum()
    comp = comp[comp > 0]
    if comp.empty:
        st.info(f"Sin datos de {pollutant} para {name(detail)} en {eea_year}.")
    else:
        fig_comp = go.Figure(go.Pie(
            labels=comp.index.tolist(), values=comp.values, hole=0.5,
            marker_colors=[SECTOR_COLORS.get(s, "#ccc") for s in comp.index],
            textinfo="label+percent", textposition="outside", automargin=True,
            hovertemplate="%{label}: %{value:,.0f} t (%{percent})<extra></extra>",
        ))
        fig_comp.update_layout(
            title=dict(text=f"Composición de {pollutant} — {name(detail)} ({eea_year})",
                       x=0.5, font=dict(size=14)),
            showlegend=False, height=380, margin=dict(t=50, l=40, r=40, b=40),
        )
        st.plotly_chart(fig_comp, width="stretch", config=PLOTLY_CONFIG)
with dc2:
    evo = dsub.groupby("year")["emissions_tonnes"].sum().reset_index()
    if evo.empty:
        st.info("Sin serie temporal disponible.")
    else:
        fig_evo = px.area(
            evo.sort_values("year"), x="year", y="emissions_tonnes",
            labels={"year": "", "emissions_tonnes": "Toneladas / año"},
            title=f"Evolución de {pollutant} — {name(detail)}",
        )
        fig_evo.update_traces(line_color="#c0392b", fillcolor="rgba(192,57,43,0.2)")
        fig_evo.update_layout(height=380, margin=dict(t=50))
        st.plotly_chart(fig_evo, width="stretch", config=PLOTLY_CONFIG)

st.divider()

if not selected:
    st.info("Selecciona países en la barra lateral para ver las gráficas siguientes.")
    st.stop()

# 2) Composición sectorial (barras apiladas)
st.subheader(f"② Composición sectorial de {pollutant}")
eea_sel = eea[
    (eea["pollutant"] == pollutant) &
    (eea["country_code"].isin(selected)) &
    (eea["sector_code"].isin(EEA_SECTORS))
].copy()
eea_sel["sector_name"] = eea_sel["sector_code"].map(EEA_SECTORS)

bar = eea_sel[eea_sel["year"] == eea_year].groupby(
    ["country_code", "sector_name"])["emissions_tonnes"].sum().reset_index()
bar["País"] = bar["country_code"].map(name)
fig2 = px.bar(
    bar, x="País", y="emissions_tonnes", color="sector_name",
    color_discrete_map=SECTOR_COLORS, barmode="stack",
    labels={"emissions_tonnes": "Toneladas", "sector_name": "Sector"},
    title=f"Emisiones de {pollutant} por sector — {eea_year}",
)
fig2.update_layout(height=440, legend_title="", legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig2, width="stretch", config=PLOTLY_CONFIG)
st.caption("Cada barra es la composición sectorial de las emisiones de "
           f"{pollutant} de un país en {eea_year}. La evolución temporal está al final.")

st.divider()

# 4) Sunburst de la cuota sectorial
st.subheader(f"③ Reparto sectorial de {pollutant} ({eea_year})")
sun = eea_sel[eea_sel["year"] == eea_year].copy()
if sun.empty:
    st.info("Sin datos para el año seleccionado.")
else:
    sun["País"] = sun["country_code"].map(name)
    fig4 = px.sunburst(
        sun, path=["País", "sector_name"], values="emissions_tonnes",
        color="sector_name", color_discrete_map=SECTOR_COLORS,
        title=f"Composición jerárquica de las emisiones de {pollutant} — {eea_year}",
    )
    fig4.update_layout(height=520, margin=dict(t=50, l=0, r=0, b=0))
    fig4.update_traces(hovertemplate="<b>%{label}</b><br>%{value:,.0f} t (%{percentParent:.0%})")
    st.plotly_chart(fig4, width="stretch", config=PLOTLY_CONFIG)
    st.caption("Anillo interior = país; anillo exterior = sectores. Haz clic en un país para ampliar.")

st.divider()

# 4) Histórico multicontaminante
st.subheader("④ Evolución a largo plazo de los contaminantes")
st.caption("Países: los seleccionados en la barra lateral.")
hist_pollutants = st.multiselect("Contaminantes a comparar", POLLUTANTS,
                                 default=[pollutant], key="hist_pollutants")
modo = st.radio("Escala", ["Índice (primer año = 100)", "Absoluto (toneladas)"],
                horizontal=True, key="hist_scale")

if not hist_pollutants:
    st.info("Selecciona al menos un contaminante.")
else:
    ep = eea[
        (eea["country_code"].isin(selected)) &
        (eea["pollutant"].isin(hist_pollutants)) &
        (eea["year"] >= 1990)
    ]
    serie = ep.groupby(["year", "country_code", "pollutant"])["emissions_tonnes"].sum().reset_index()
    if serie.empty:
        st.info("Sin datos de emisiones para la selección.")
    else:
        serie = serie.sort_values("year")
        serie["País"] = serie["country_code"].map(name)
        if modo.startswith("Índice"):
            base = serie.groupby(["country_code", "pollutant"])["emissions_tonnes"].transform("first")
            serie["valor"] = serie["emissions_tonnes"] / base.replace(0, np.nan) * 100
            ylab = "Índice (primer año = 100)"
        else:
            serie["valor"] = serie["emissions_tonnes"]
            ylab = "Toneladas / año"
        facet_kw = dict(facet_col="pollutant", facet_col_wrap=2) if len(hist_pollutants) > 1 else {}
        fig_hist = px.line(
            serie, x="year", y="valor", color="País", markers=True,
            labels={"year": "", "valor": ylab}, **facet_kw,
        )
        fig_hist.update_layout(
            height=520 if len(hist_pollutants) > 1 else 440,
            hovermode="x unified", legend_title="",
        )
        fig_hist.update_yaxes(matches=None)  # cada contaminante con su propia escala
        fig_hist.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        st.plotly_chart(fig_hist, width="stretch", config=PLOTLY_CONFIG)
        st.caption("Suma de todos los sectores. El índice (primer año = 100) permite comparar "
                   "el ritmo de reducción entre contaminantes de magnitudes muy distintas "
                   "(p. ej. el SO₂ ha caído mucho más que el NH₃ agrícola).")

st.divider()

# 5) Ranking de descarbonización
st.subheader("⑤ Ranking de descarbonización eléctrica")
cy = country_year()
decoup = compute_decoupling_rate(cy, min(PM25_YEARS), max(PM25_YEARS))
decoup = decoup[decoup["country"].isin(selected)].sort_values("pct_change")
if decoup.empty:
    st.info("Sin datos suficientes.")
else:
    decoup["País"] = decoup["country"].map(name)
    colors = ["#27ae60" if v < 0 else "#e74c3c" for v in decoup["pct_change"]]
    fig5 = go.Figure(go.Bar(
        x=decoup["pct_change"], y=decoup["País"], orientation="h",
        marker_color=colors,
        text=[f"{v:+.1f}%" for v in decoup["pct_change"]], textposition="outside",
        hovertemplate="%{y}: %{x:+.1f}%<extra></extra>",
    ))
    fig5.add_vline(x=0, line_dash="dash", line_color="black", line_width=1)
    fig5.update_layout(
        height=420,
        title=f"Cambio de intensidad de carbono {min(PM25_YEARS)}→{max(PM25_YEARS)} "
              "(verde = mejora)",
        xaxis_title="% de cambio", margin=dict(l=10, r=40, t=50, b=10),
    )
    st.plotly_chart(fig5, width="stretch", config=PLOTLY_CONFIG)

st.divider()

# 6) Dispersión intensidad de carbono vs PM2.5
sc_year = min(max(eea_year, min(PM25_YEARS)), max(PM25_YEARS))
st.subheader(f"⑥ ¿Electricidad sucia ⇒ peor aire? — {sc_year}")
cy_y = cy[cy["year"] == sc_year][["country", "carbon_intensity_mean", "renewable_share_mean"]]
pm_y = pm25()[pm25()["year"] == sc_year][["country", "pm25_mean"]]
sc = cy_y.merge(pm_y, on="country", how="inner").dropna(
    subset=["carbon_intensity_mean", "pm25_mean"])
if len(sc) < 2:
    st.info("Datos insuficientes para la dispersión.")
else:
    sc["País"] = sc["country"].map(name)
    sc["Renovable %"] = (sc["renewable_share_mean"] * 100).round(0)
    fig6 = px.scatter(
        sc, x="carbon_intensity_mean", y="pm25_mean", text="País",
        color="Renovable %", color_continuous_scale="RdYlGn",
        labels={"carbon_intensity_mean": "Intensidad de carbono (gCO₂/kWh)",
                "pm25_mean": "PM2.5 media (µg/m³)"},
        title=f"Intensidad de carbono frente a PM2.5 — {sc_year}",
    )
    fig6.update_traces(textposition="top center", marker=dict(size=13, line=dict(width=1, color="#333")))
    # Recta de tendencia + coeficiente de correlación.
    x, y = sc["carbon_intensity_mean"].values, sc["pm25_mean"].values
    z = np.polyfit(x, y, 1)
    xl = np.linspace(x.min(), x.max(), 50)
    fig6.add_trace(go.Scatter(x=xl, y=np.polyval(z, xl), mode="lines",
                              line=dict(dash="dash", color="#c0392b"), name="Tendencia"))
    r = np.corrcoef(x, y)[0, 1]
    fig6.add_hline(y=5, line_dash="dot", line_color="#2ecc71",
                   annotation_text="Directriz OMS (5 µg/m³)", annotation_position="top left")
    fig6.add_annotation(xref="paper", yref="paper", x=0.98, y=0.98,
                        text=f"r = {r:.2f}", showarrow=False,
                        font=dict(size=14, color="#c0392b"),
                        bgcolor="white", bordercolor="#c0392b")
    fig6.update_layout(height=520)
    st.plotly_chart(fig6, width="stretch", config=PLOTLY_CONFIG)
    st.caption(
        "Color = cuota renovable. Una correlación débil confirma que la calidad del aire "
        "depende de muchos sectores además de la electricidad."
    )
