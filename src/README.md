# `src/` — módulos compartidos

Estos módulos los usan **tanto la app como el pipeline de datos** (`scripts/`).

| Módulo | Qué hace | Usado por |
|---|---|---|
| `config.py` | Rutas y constantes: países y nombres, factores de emisión (IPCC AR6), grupos de fuente y colores, sectores EEA, conversión de divisas, años, URL de NUTS. | app + pipeline |
| `data_loaders.py` | Lectura de datos. Para la **app**: `load_app_*` (Parquet/GeoJSON de `data/app/`) y APIs en vivo (`load_generation_live_fraunhofer` de Energy-Charts, `load_generation_live` de ENTSO-E de respaldo, `fetch_openaq_pm25_latest` de OpenAQ). Para el **pipeline**: lectores de los Parquet completos (`load_*_historical`, `load_geodataframe`). | app + pipeline |
| `processing.py` | Cálculos sobre los datos. La **app** usa `compute_carbon_intensity` (mezcla en vivo), `rank_dominant_sector` y `compute_decoupling_rate`. El **pipeline** usa además `aggregate_to_country_year` / `aggregate_to_country_month` para preagregar a `data/app/`. | app + pipeline |

La app **no** necesita geopandas/GDAL en ejecución: `data_loaders` lo importa de forma
**perezosa** solo dentro de `load_geodataframe`, que únicamente usa el pipeline. Por eso
`requirements.txt` (web) es ligero y las dependencias pesadas están en `requirements-pipeline.txt`.

No se incluyen `charts.py`/`maps.py` ni los scripts `06/07`: generan las figuras del **informe**
estático y no forman parte de la cadena de datos que consume la web.
