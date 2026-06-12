# Energía y calidad del aire en Europa

Aplicación web interactiva que relaciona cómo Europa **produce electricidad** con la
**calidad del aire (PM2.5)** que respira, en 26 países (2019–2024). Combina **datos
históricos** (descargados y preagregados fuera de línea) con **dos APIs en tiempo real**.
Proyecto de la asignatura *Visualización de Datos* (MIARFID, Universitat Politècnica de València).

> **Histórico** = la web lee ficheros ligeros ya preparados en `data/app/`; **no llama a
> ninguna API**. **En vivo** = la web consulta una API en el momento.

## Páginas

| Página | Datos | Contenido |
|---|---|---|
| **Inicio** | en vivo | Presentación, flujo de datos e **instantánea de generación en vivo** (Energy-Charts) con selector de país y periodo. |
| **Mapa interactivo** | histórico | Coropleta parametrizable (intensidad de carbono / renovables / PM2.5 / precio) × año × estilo (coropleta, **bivariante** con leyenda en matriz 3×3, **ráster 1 km**). Clic en un país → ficha con métricas y mezcla; ranking 5↑/5↓. |
| **Evolución** | histórico | Series mensuales, mezcla apilada, **dispersión animada** carbono↔PM2.5, **mapa animado** por año, **mapa de calor** hora×mes y precios/volatilidad. |
| **Fuentes y emisiones** | histórico | Mapa de sector dominante con **detalle al clic** (composición y evolución del país), composición sectorial, **sunburst**, **evolución multicontaminante** desde 1990, descarbonización y dispersión carbono–PM2.5. |
| **Comparativa** | histórico | **Radar** de perfiles, **treemap** de generación, **rango** de PM2.5 dentro de cada país y **reloj** de la mejor hora para consumir. |
| **Tiempo real** | en vivo | Mapa de intensidad de carbono en vivo (Energy-Charts) + **PM2.5 medida ahora** por estaciones (OpenAQ). |

## Fuentes de datos

**Históricos** (se descargan con el *pipeline* offline, se limpian y se preagregan a Parquet;
la app solo lee `data/app/`, **sin llamar a APIs**):

- **ENTSO-E Transparency Platform** — generación eléctrica horaria y precios día-anterior
  (descarga con la librería `entsoe-py`).
- **Agencia Europea de Medio Ambiente (EEA)** — ráster de PM2.5 interpolado a 1 km e
  inventario sectorial de emisiones (CLRTAP: PM2.5, NOx, NH3, SO2).
- **Eurostat GISCO** — contornos administrativos NUTS-0.

**En tiempo real** (APIs que consulta la web en ejecución):

- **Energy-Charts / Fraunhofer ISE** — generación en vivo, **sin clave** (fuente primaria).
- **OpenAQ** — mediciones de PM2.5 en vivo por estación.
- **ENTSO-E** interviene **solo como respaldo** del tiempo real si Energy-Charts no responde
  (y existe `ENTSOE_API_KEY`); no es necesario para que la web funcione.

## Ejecutar en local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   ·   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/Home.py
```

La app arranca con los datos ya incluidos en `data/app/`; **no requiere descargas ni claves**
para las vistas históricas.

## Claves de API (opcionales)

Los datos en tiempo real funcionan **sin clave** (Energy-Charts). Para habilitar la capa de
calidad del aire y el respaldo, copia `.streamlit/secrets.toml.example` a
`.streamlit/secrets.toml` y rellena:

| Clave | Para qué | Sin ella |
|---|---|---|
| `OPENAQ_API_KEY` | Capa de **PM2.5 en vivo** (OpenAQ, gratis en [openaq.org](https://openaq.org)). | Se oculta esa sección. |
| `ENTSOE_API_KEY` | **Respaldo** de generación en vivo vía ENTSO-E. | Se usa solo Energy-Charts. |

## Desplegar en Streamlit Cloud

1. Sube esta carpeta a un repositorio de GitHub (todo, incluido `data/app/`).
2. En [share.streamlit.io](https://share.streamlit.io) → *New app*, selecciona el repo y
   como *Main file path* indica **`app/Home.py`**.
3. *(Opcional)* En *Advanced settings → Secrets*, pega el contenido de tu
   `secrets.toml` (`OPENAQ_API_KEY`, `ENTSOE_API_KEY`).
4. *Deploy*. La app es pública y no requiere registro para visitarla.

## Reproducir los datos (pipeline)

La web solo necesita `data/app/` (ya incluido). Si quieres **regenerarlo desde las fuentes
originales**, ejecuta el *pipeline* (necesita dependencias extra y la clave de ENTSO-E):

```bash
pip install -r requirements-pipeline.txt   # geopandas, rasterio, entsoe-py…
python scripts/01_download_geo.py            # contornos NUTS-0 (Eurostat)
python scripts/02_download_entsoe.py         # generación y precios (ENTSO-E, varias horas)
python scripts/03_download_eea.py            # inventario de emisiones (EEA/Eurostat)
python scripts/04_process_eea_raster.py     # ráster PM2.5 1 km → estadísticas por país
python scripts/05_build_parquet.py           # CSV crudos → Parquet (data/processed/)
python scripts/06_build_app_data.py          # preagrega todo → data/app/  (lo que usa la web)
```

**Nota sobre el ráster PM2.5:** `04_process_eea_raster.py` no descarga los GeoTIFF (son muy grandes); espera que
estén en `data/interpolated/<…>_<año>_…/pm25_avg*.tif`. Se descargan a mano del visor de la EEA
*Air Quality – statistics and maps* (rejilla interpolada PM2.5, 1 km, EPSG:3035), uno por año
2019–2024: <https://www.eea.europa.eu/en/analysis/maps-and-charts>.

Cada paso documenta su fuente. Los datos crudos e intermedios (`data/raw`, `data/processed`,
`data/geo`, `data/interpolated`) son pesados y **no se versionan**: se regeneran al ejecutar
el *pipeline*. El resultado final, `data/app/` (~3 MB), sí se incluye.

## Estructura

```
app/
  Home.py            página de inicio + generación en vivo
  components.py      cargadores cacheados, gráficos y mapas, acceso a las APIs en vivo
  pages/             las 5 secciones (multipágina de Streamlit)
src/                 módulos compartidos por la app y el pipeline (ver src/README.md)
  config.py          rutas y constantes (países, factores de emisión, grupos de fuente)
  data_loaders.py    lectura de datos (data/app/, Parquet completos) y APIs en vivo
  processing.py      cálculos (intensidad de carbono, sectores, agregaciones)
scripts/             pipeline de descarga y preprocesado → data/app/
data/app/            datos ligeros pre-agregados (~3 MB) — únicos datos que usa la app
requirements.txt     dependencias de la web · requirements-pipeline.txt: extras del pipeline
.streamlit/          tema y plantilla de secretos
docs/librerias.md    librerías utilizadas (entregable de la asignatura)
```

## Librerías

Ver [docs/librerias.md](docs/librerias.md). La app de ejecución es ligera (sin geopandas/GDAL):
los mapas se renderizan con **Plotly** sobre un GeoJSON ya simplificado, más **Folium** para la
capa ráster. Rendimiento: todos los datos y llamadas a API se **cachean** (`st.cache_data`), de
modo que al mover un widget no se recalcula ni se vuelve a descargar nada innecesariamente.

Autor: **Blai Puchol Salort** — MIARFID, UPV.
