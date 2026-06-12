import json
import pandas as pd
from src.config import DATA_PROCESSED, DATA_GEO, DATA_APP, COUNTRIES

# NOTA: geopandas se importa de forma perezosa dentro de load_geodataframe().
# Así la app de Streamlit (que solo usa data/app/ y el GeoJSON ya simplificado)
# no necesita geopandas/GDAL en el despliegue en la nube.


# ── Datos ligeros pre-agregados para la app (data/app) ────────────────────────
# Generados por scripts/06_build_app_data.py. Es lo único que necesita la app en
# tiempo de ejecución; no carga los Parquet pesados de data/processed.

def _read_app_parquet(name: str) -> pd.DataFrame:
    path = DATA_APP / name
    if not path.exists():
        raise FileNotFoundError(
            f"Falta {path}. Ejecuta antes: python scripts/06_build_app_data.py"
        )
    return pd.read_parquet(path)


def load_app_country_year() -> pd.DataFrame:
    return _read_app_parquet("country_year.parquet")


def load_app_country_month() -> pd.DataFrame:
    return _read_app_parquet("country_month.parquet")


def load_app_fuel_mix_year() -> pd.DataFrame:
    return _read_app_parquet("fuel_mix_country_year.parquet")


def load_app_fuel_mix_month() -> pd.DataFrame:
    return _read_app_parquet("fuel_mix_country_month.parquet")


def load_app_hourly_profile() -> pd.DataFrame:
    return _read_app_parquet("hourly_profile.parquet")


def load_app_prices_year() -> pd.DataFrame:
    return _read_app_parquet("prices_country_year.parquet")


def load_app_prices_month() -> pd.DataFrame:
    return _read_app_parquet("prices_country_month.parquet")


def load_app_pm25() -> pd.DataFrame:
    return _read_app_parquet("pm25_country_all.parquet")


def load_app_emissions() -> pd.DataFrame:
    return _read_app_parquet("eea_emissions.parquet")


def load_app_geojson() -> dict:
    """Devuelve el GeoJSON NUTS-0 simplificado como dict (sin geopandas)."""
    path = DATA_APP / "nuts0_simplified.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"Falta {path}. Ejecuta antes: python scripts/06_build_app_data.py"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_generation_historical() -> pd.DataFrame:
    path = DATA_PROCESSED / "generation_all.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Ejecuta primero scripts/05_build_parquet.py. Falta: {path}")
    return pd.read_parquet(path)


def load_prices_historical() -> pd.DataFrame:
    path = DATA_PROCESSED / "prices_all.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Ejecuta primero scripts/05_build_parquet.py. Falta: {path}")
    return pd.read_parquet(path)


def load_openaq_historical() -> pd.DataFrame:
    path = DATA_PROCESSED / "openaq_all.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Falta: {path}")
    return pd.read_parquet(path)


def load_eea_emissions() -> pd.DataFrame:
    path = DATA_PROCESSED / "eea_emissions.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Ejecuta primero scripts/05_build_parquet.py. Falta: {path}")
    return pd.read_parquet(path)


def load_geodataframe(level: int = 0):
    import geopandas as gpd
    path = DATA_GEO / f"nuts{level}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"Ejecuta primero scripts/01_download_geo.py. Falta: {path}")
    gdf = gpd.read_file(path)
    if "NUTS_ID" in gdf.columns:
        gdf = gdf[gdf["NUTS_ID"].str[:2].isin(COUNTRIES)].copy()
    elif "CNTR_CODE" in gdf.columns:
        gdf = gdf[gdf["CNTR_CODE"].isin(COUNTRIES)].copy()
        gdf = gdf.rename(columns={"CNTR_CODE": "NUTS_ID"})
    return gdf


def load_generation_live(client, country: str, days: int = 1) -> pd.DataFrame:
    """Consulta a ENTSO-E los últimos `days` días de generación (usado por la app)."""
    try:
        start = pd.Timestamp.now(tz="Europe/Brussels") - pd.Timedelta(days=days)
        end = pd.Timestamp.now(tz="Europe/Brussels")
        return client.query_generation(country, start=start, end=end)
    except Exception as e:
        print(f"ENTSO-E live falló para {country}: {e}")
        return pd.DataFrame()


def fetch_openaq_pm25_latest(api_key: str, hours: int = 3, max_pages: int = 12,
                             europe_bbox=(-25.0, 34.0, 45.0, 72.0)) -> pd.DataFrame:
    """Últimas mediciones de PM2.5 (OpenAQ v3) filtradas a Europa.

    Usa el endpoint /v3/parameters/2/latest (parameters_id=2 = PM2.5), que solo
    devuelve estaciones con dato reciente. Pagina una ventana corta y filtra por
    coordenadas al recuadro europeo. Devuelve columnas: lat, lon, pm25, datetime,
    location_id. DataFrame vacío si no hay clave o falla la API.
    """
    import datetime as dt
    import requests

    if not api_key:
        return pd.DataFrame(columns=["lat", "lon", "pm25", "datetime", "location_id"])

    lon_min, lat_min, lon_max, lat_max = europe_bbox
    dmin = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"X-API-Key": api_key}
    rows = []
    for page in range(1, max_pages + 1):
        try:
            r = requests.get(
                "https://api.openaq.org/v3/parameters/2/latest",
                headers=headers,
                params={"datetime_min": dmin, "limit": 1000, "page": page},
                timeout=20,
            )
            if r.status_code != 200:
                break
            results = r.json().get("results", [])
        except Exception as e:
            print(f"OpenAQ falló (página {page}): {e}")
            break
        if not results:
            break
        for x in results:
            coord = x.get("coordinates") or {}
            lat, lon = coord.get("latitude"), coord.get("longitude")
            value = x.get("value")
            if lat is None or lon is None or value is None:
                continue
            if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
                continue
            if value < 0 or value > 1000:  # descartar valores absurdos
                continue
            rows.append({
                "lat": lat, "lon": lon, "pm25": value,
                "datetime": (x.get("datetime") or {}).get("utc"),
                "location_id": x.get("locationsId"),
            })
        if len(results) < 1000:
            break
    return pd.DataFrame(rows)


def load_generation_live_fraunhofer(country: str, days: int = 1) -> pd.DataFrame:
    """Fuente de generación en vivo (Energy-Charts, Fraunhofer ISE), últimos `days` días.

    Una sola petición, sin reintentos. Si el país no está cubierto (404) o se alcanza
    el límite de peticiones (429), devuelve vacío y la app recurre al respaldo histórico.
    """
    import requests

    url = "https://api.energy-charts.info/public_power"
    params = {
        "country": country.lower(),
        "start": (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%dT%H:%M"),
        "end": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M"),
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code in (404, 429):
            return pd.DataFrame()
        resp.raise_for_status()
        data = resp.json()

        times = data.get("unix_seconds", [])
        if not times:
            return pd.DataFrame()

        records = {}
        for series in data.get("production_types", []):
            series_name = series.get("name", "Unknown")
            records[series_name] = series.get("data", [])

        df = pd.DataFrame(records, index=pd.to_datetime(times, unit="s", utc=True))
        df.index = df.index.tz_convert("Europe/Brussels")
        return df
    except requests.exceptions.RequestException:
        return pd.DataFrame()
