import streamlit as st

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

- **Generación e intensidad de carbono** ahora mismo — *Energy-Charts / Fraunhofer ISE* (sin clave)
- **PM2.5 medida en estaciones** — *OpenAQ*
"""
)

# Tarjetas de navegación
st.markdown("### Explora")
c1, c2, c3, c4, c5 = st.columns(5)
c1.info("**Mapa interactivo**\n\nCoropletas de intensidad de carbono, renovables, PM2.5 y precios, con selector de parámetro, año y estilo.")
c2.success("**Evolución**\n\nSeries temporales, mapa animado por año y mapa de calor hora×mes.")
c3.warning("**Fuentes y emisiones**\n\n¿Qué sector ensucia el aire? Atribución sectorial EEA, descarbonización e histórico.")
c4.error("**Comparativa**\n\nRadar de perfiles, treemap de generación, dispersión de PM2.5 y mejor hora para consumir.")
c5.info("**Tiempo real**\n\nGeneración e intensidad de carbono en vivo (24 h / semana / mes), mapa europeo y PM2.5 por estaciones (OpenAQ).")

st.divider()

st.caption(
    "Proyecto de la asignatura *Visualización de Datos* — MIARFID, Universitat Politècnica "
    "de València. Autor: Blai Puchol Salort. Datos: ENTSO-E, EEA, Eurostat GISCO, "
    "Energy-Charts (Fraunhofer) y OpenAQ."
)
