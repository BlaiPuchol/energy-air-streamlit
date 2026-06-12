"""Pre-agrega los Parquet pesados en ficheros ligeros para la app de Streamlit.

La app NO carga `generation_all.parquet` (~173 MB) ni los rasters (~729 MB) en
tiempo de ejecución: lee únicamente los ficheros pequeños que genera este script
en `data/app/` (unos pocos MB en total), de modo que el despliegue en Streamlit
Cloud sea viable y el arranque rápido.

Ejecutar (con el entorno completo: geopandas, pyarrow) después del pipeline:

    python scripts/06_build_app_data.py
"""
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import geopandas as gpd

from src.config import (
    DATA_PROCESSED, DATA_APP, COUNTRIES, PM25_YEARS,
    FUEL_GROUPS, NON_EUR_PRICE_ZONES, CURRENCY_TO_EUR,
)
from src.processing import (
    aggregate_to_country_year,
    aggregate_to_country_month,
)


def _load_generation() -> pd.DataFrame:
    path = DATA_PROCESSED / "generation_all.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}. Ejecuta antes scripts/05_build_parquet.py.")
    gen = pd.read_parquet(path)
    if not isinstance(gen.index, pd.DatetimeIndex):
        gen.index = pd.to_datetime(gen.index)
    return gen


def build_country_aggregates(gen: pd.DataFrame):
    """country_year.parquet y country_month.parquet (intensidad de carbono, renovables)."""
    cy = aggregate_to_country_year(gen)
    cm = aggregate_to_country_month(gen)
    cy["year"] = cy["year"].astype(int)
    cm["year"] = cm["year"].astype(int)
    cm["month"] = cm["month"].astype(int)
    cy.to_parquet(DATA_APP / "country_year.parquet", index=False)
    cm.to_parquet(DATA_APP / "country_month.parquet", index=False)
    print(f"  country_year.parquet: {len(cy)} filas")
    print(f"  country_month.parquet: {len(cm)} filas")


def _fuel_group_long(gen: pd.DataFrame, freq_cols: list) -> pd.DataFrame:
    """Suma la generación por grupo de combustible (formato largo) en GWh.

    `freq_cols` son las columnas temporales de agrupación (['year'] o ['year','month']).
    """
    df = gen.copy()
    df["year"] = df.index.year
    if "month" in freq_cols:
        df["month"] = df.index.month

    # Energía (GWh) por grupo = media horaria (MW) * horas / 1000; aquí sumamos MWh.
    records = []
    group_keys = ["country"] + freq_cols
    grouped = df.groupby(group_keys)
    for group_name, sub in grouped:
        row = dict(zip(group_keys, group_name if isinstance(group_name, tuple) else (group_name,)))
        for group, cols in FUEL_GROUPS.items():
            present = [c for c in cols if c in sub.columns]
            # Cada fila horaria son MW durante 1 h ≈ MWh → /1000 = GWh.
            gwh = sub[present].clip(lower=0).sum().sum() / 1000 if present else 0.0
            rec = dict(row)
            rec["fuel_group"] = group
            rec["gwh"] = round(float(gwh), 3)
            records.append(rec)
    out = pd.DataFrame(records)
    for col in ("year", "month"):
        if col in out.columns:
            out[col] = out[col].astype(int)
    return out


def build_fuel_mix(gen: pd.DataFrame):
    """fuel_mix_country_year.parquet y fuel_mix_country_month.parquet."""
    fy = _fuel_group_long(gen, ["year"])
    fm = _fuel_group_long(gen, ["year", "month"])
    fy.to_parquet(DATA_APP / "fuel_mix_country_year.parquet", index=False)
    fm.to_parquet(DATA_APP / "fuel_mix_country_month.parquet", index=False)
    print(f"  fuel_mix_country_year.parquet: {len(fy)} filas")
    print(f"  fuel_mix_country_month.parquet: {len(fm)} filas")


def build_hourly_profile(gen: pd.DataFrame):
    """hourly_profile.parquet: perfil medio por país, mes y hora del día."""
    df = gen.copy()
    df["month"] = df.index.month
    df["hour"] = df.index.hour
    prof = df.groupby(["country", "month", "hour"]).agg(
        carbon_intensity_mean=("carbon_intensity_gco2_kwh", "mean"),
        renewable_share_mean=("renewable_share", "mean"),
    ).reset_index()
    prof["month"] = prof["month"].astype(int)
    prof["hour"] = prof["hour"].astype(int)
    prof.to_parquet(DATA_APP / "hourly_profile.parquet", index=False)
    print(f"  hourly_profile.parquet: {len(prof)} filas")


def _normalize_prices_to_eur(prices: pd.DataFrame) -> pd.DataFrame:
    """Convierte PL/RO/BG de moneda local a EUR según el año (tipos del BCE)."""
    df = prices.copy()
    df["year"] = df.index.year
    for country, years in NON_EUR_PRICE_ZONES.items():
        for year in years:
            rate = CURRENCY_TO_EUR.get((country, year))
            if rate is None:
                continue
            mask = (df["country"] == country) & (df["year"] == year)
            df.loc[mask, "price_eur_mwh"] = df.loc[mask, "price_eur_mwh"] / rate
    return df


def build_prices():
    """prices_country_year.parquet y prices_country_month.parquet."""
    path = DATA_PROCESSED / "prices_all.parquet"
    if not path.exists():
        print("  prices_all.parquet no encontrado — se omite.")
        return
    prices = pd.read_parquet(path)
    if not isinstance(prices.index, pd.DatetimeIndex):
        prices.index = pd.to_datetime(prices.index)
    prices = _normalize_prices_to_eur(prices)
    prices["month"] = prices.index.month

    py = prices.groupby(["country", "year"]).agg(
        price_mean=("price_eur_mwh", "mean"),
        price_median=("price_eur_mwh", "median"),
        price_std=("price_eur_mwh", "std"),
    ).reset_index()
    pm = prices.groupby(["country", "year", "month"]).agg(
        price_mean=("price_eur_mwh", "mean"),
        price_std=("price_eur_mwh", "std"),
    ).reset_index()
    py["year"] = py["year"].astype(int)
    pm["year"] = pm["year"].astype(int)
    pm["month"] = pm["month"].astype(int)
    py.to_parquet(DATA_APP / "prices_country_year.parquet", index=False)
    pm.to_parquet(DATA_APP / "prices_country_month.parquet", index=False)
    print(f"  prices_country_year.parquet: {len(py)} filas")
    print(f"  prices_country_month.parquet: {len(pm)} filas")


def build_pm25():
    """pm25_country_all.parquet: une los pm25_country_<año>.parquet con columna 'year'."""
    frames = []
    for year in PM25_YEARS:
        path = DATA_PROCESSED / f"pm25_country_{year}.parquet"
        if not path.exists():
            print(f"  pm25_country_{year}.parquet no encontrado — se omite.")
            continue
        df = pd.read_parquet(path)
        df["year"] = year
        frames.append(df)
    if not frames:
        print("  Sin datos PM2.5 — se omite.")
        return
    allpm = pd.concat(frames, ignore_index=True)
    allpm = allpm[allpm["country"].isin(COUNTRIES)].copy()
    allpm.to_parquet(DATA_APP / "pm25_country_all.parquet", index=False)
    print(f"  pm25_country_all.parquet: {len(allpm)} filas")


def build_emissions():
    """Copia eea_emissions.parquet (ya es pequeño, ~0.07 MB)."""
    src = DATA_PROCESSED / "eea_emissions.parquet"
    if src.exists():
        shutil.copy(src, DATA_APP / "eea_emissions.parquet")
        print("  eea_emissions.parquet: copiado")
    else:
        print("  eea_emissions.parquet no encontrado — se omite.")


def build_geojson():
    """nuts0_simplified.geojson: contornos NUTS-0 simplificados (sin geopandas en runtime)."""
    from src.config import DATA_GEO
    path = DATA_GEO / "nuts0.geojson"
    if not path.exists():
        print("  nuts0.geojson no encontrado — se omite.")
        return
    gdf = gpd.read_file(path)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    # NUTS usa "EL" para Grecia y "UK" para Reino Unido; los datos de energía
    # (ENTSO-E) usan "GR"/"GB". Remapeamos para que Grecia case con su polígono.
    gdf["NUTS_ID"] = gdf["NUTS_ID"].replace({"EL": "GR", "UK": "GB"})
    gdf = gdf[gdf["NUTS_ID"].str[:2].isin(COUNTRIES)].copy()
    name_col = "NAME_LATN" if "NAME_LATN" in gdf.columns else "NUTS_ID"
    gdf = gdf[["NUTS_ID", name_col, "geometry"]].rename(columns={name_col: "name"})
    gdf["geometry"] = gdf["geometry"].simplify(0.02, preserve_topology=True)
    out = DATA_APP / "nuts0_simplified.geojson"
    gdf.to_file(out, driver="GeoJSON")
    size_kb = out.stat().st_size / 1024
    print(f"  nuts0_simplified.geojson: {len(gdf)} países, {size_kb:.0f} KB")


def build_raster_previews():
    """Copia los PNG de previsualización del raster PM2.5 y sus bounds (1 km, ligeros)."""
    n = 0
    for year in PM25_YEARS:
        for stem in (f"pm25_raster_preview_{year}.png", f"pm25_raster_bounds_{year}.txt"):
            src = DATA_PROCESSED / stem
            if src.exists():
                shutil.copy(src, DATA_APP / stem)
                n += 1
    print(f"  rasters PM2.5: {n} ficheros copiados")


def main():
    DATA_APP.mkdir(parents=True, exist_ok=True)
    print(f"Generando datos ligeros para la app en {DATA_APP} ...\n")

    gen = _load_generation()
    print(f"Generación cargada: {len(gen):,} filas horarias\n")

    build_country_aggregates(gen)
    build_fuel_mix(gen)
    build_hourly_profile(gen)
    build_prices()
    build_pm25()
    build_emissions()
    build_geojson()
    build_raster_previews()

    total = sum(f.stat().st_size for f in DATA_APP.glob("*") if f.is_file())
    print(f"\nListo. Tamaño total de data/app/: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
