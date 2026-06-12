# Librerías utilizadas — Web de visualización

**Proyecto:** Energía y calidad del aire en Europa · *Visualización de Datos* (MIARFID, UPV)
**Autor:** Blai Puchol Salort

Este documento recoge las librerías adicionales necesarias para ejecutar la página web
en local sin problemas, tal como pide el enunciado. Se distinguen las de **ejecución de
la app** (las únicas que necesita Streamlit Cloud) de las del **pipeline de datos**.

## Ejecución de la app (`requirements.txt`)

| Librería | Para qué se usa |
|---|---|
| **streamlit** (≥1.36) | Framework de la web: páginas, widgets, caché (`st.cache_data`/`st.cache_resource`). |
| **pandas** (≥2.0) | Carga y manipulación de los datos pre-agregados (Parquet). |
| **numpy** | Cálculos numéricos (terciles del mapa bivariante, recta de regresión). |
| **pyarrow** | Motor de lectura de los ficheros Parquet. |
| **plotly** (≥6.0) | Todas las gráficas y la mayoría de mapas, incluidos los de teselas MapLibre (`choropleth_map`/`scatter_map`): coropletas, animación, sunburst, heatmap, gauge, radar, treemap, dispersión. |
| **folium** (≥0.17) | Mapa con la capa raster PM2.5 de 1 km superpuesta (`ImageOverlay`). |
| **streamlit-folium** | Integración de los mapas Folium dentro de Streamlit. |
| **branca** (≥0.7) | Dependencia de Folium para colores y elementos HTML (leyendas). |
| **requests** | Llamadas a las APIs en vivo (Energy-Charts y OpenAQ). |
| **python-dotenv** | Carga de variables de entorno (`.env`) en local. |
| **Pillow** (≥10.0) | Genera la leyenda 3×3 del mapa bivariante y maneja los PNG del raster. |
| **entsoe-py** | *Opcional.* Respaldo de datos en vivo vía ENTSO-E si se define `ENTSOE_API_KEY`. |

> La app **no** necesita geopandas ni GDAL: los contornos NUTS-0 se sirven ya
> simplificados como GeoJSON plano y los datos pesados se pre-agregan fuera de línea.
> Esto mantiene el despliegue en Streamlit Cloud ligero y rápido.

## Pipeline de datos (`requirements-pipeline.txt`)

Solo se necesitan para **regenerar los datos** desde las fuentes originales (carpeta
`scripts/`), no para visitar la web:

| Librería | Para qué se usa |
|---|---|
| **entsoe-py** | Descarga de generación y precios de ENTSO-E (`02_download_entsoe.py`). |
| **geopandas** | Contornos NUTS-0: descarga, filtro y simplificación (`01`, `04`, `06`). |
| **rasterio**, **rasterstats** | Procesado del raster GeoTIFF PM2.5 (1 km) y estadísticas zonales por país (`04`). |
| **matplotlib** | PNG de previsualización del raster para Folium (`04`). |

## Cómo ejecutar en local

```powershell
# 1) Entorno e instalación (solo la app):
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2) Lanzar la web (usa los datos ya incluidos en data/app/):
streamlit run app/Home.py
```

Para **regenerar `data/app/`** desde las fuentes originales (opcional):

```powershell
pip install -r requirements-pipeline.txt
python scripts/01_download_geo.py          # contornos NUTS-0 (Eurostat)
python scripts/02_download_entsoe.py       # generación y precios (ENTSO-E)
python scripts/03_download_eea.py          # inventario de emisiones (EEA)
python scripts/04_process_eea_raster.py   # raster PM2.5 1 km → estadísticas por país
python scripts/05_build_parquet.py         # CSV crudos → Parquet
python scripts/06_build_app_data.py        # preagrega todo → data/app/
```

## Fuentes de datos

- **ENTSO-E Transparency Platform** — generación horaria y precios día-anterior.
- **European Environment Agency (EEA)** — raster PM2.5 (1 km) e inventario sectorial CLRTAP.
- **Eurostat GISCO** — contornos administrativos NUTS-0.
- **Energy-Charts (Fraunhofer ISE)** — generación eléctrica en tiempo real (API pública sin clave).
- **OpenAQ** — mediciones de PM2.5 en tiempo real por estación (API v3, clave gratuita). Se
  consume con `requests`, sin librería adicional.
