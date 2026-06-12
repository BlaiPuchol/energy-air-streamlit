"""Consolida los CSV crudos en ficheros Parquet limpios.

Ejecutar después de las descargas.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.config import DATA_RAW, DATA_PROCESSED, COUNTRIES, EMISSION_FACTORS
from src.processing import compute_carbon_intensity


def build_generation_parquet():
    print("Construyendo Parquet de generación...")
    dfs = []
    for country in COUNTRIES:
        path = DATA_RAW / f"generation_{country}.csv"
        if path.exists():
            df = pd.read_csv(path, index_col=0, parse_dates=True, low_memory=False)
            # entsoe-py devuelve columnas MultiIndex (actual, forecast) — nos quedamos con la real.
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs("Actual", axis=1, level=1, drop_level=True)
            for col in df.columns:
                if col in EMISSION_FACTORS:
                    series = df[col]
                    if series.dtype == "object":
                        series = series.astype(str).str.replace(",", ".", regex=False)
                    df[col] = pd.to_numeric(series, errors="coerce")
            df = compute_carbon_intensity(df)
            df["country"] = country
            dfs.append(df)
            print(f"  {country}: {len(df)} filas")
        else:
            print(f"  {country}: NO ENCONTRADO — se omite")

    if dfs:
        combined = pd.concat(dfs).sort_index()
        out = DATA_PROCESSED / "generation_all.parquet"
        combined.to_parquet(out)
        print(f"\nGuardado: {out} ({len(combined):,} filas)")
    else:
        print("  No hay datos de generación. Ejecuta antes 02_download_entsoe.py.")


def build_prices_parquet():
    print("\nConstruyendo Parquet de precios...")
    dfs = []
    for country in COUNTRIES:
        path = DATA_RAW / f"prices_{country}.csv"
        if path.exists():
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            if isinstance(df, pd.Series) or df.shape[1] == 1:
                df = df.squeeze().to_frame(name="price_eur_mwh")
            df["country"] = country
            dfs.append(df)

    if dfs:
        combined = pd.concat(dfs).sort_index()
        out = DATA_PROCESSED / "prices_all.parquet"
        combined.to_parquet(out)
        print(f"Guardado: {out} ({len(combined):,} filas)")
    else:
        print("  No hay datos de precios.")


def build_eea_parquet():
    print("\nConstruyendo Parquet EEA...")
    path = DATA_RAW / "eea_emissions.csv"
    if not path.exists():
        print("  eea_emissions.csv no encontrado. Ejecuta antes 03_download_eea.py.")
        return

    df = pd.read_csv(path, encoding="latin1", low_memory=False)
    print(f"  Cargado: {df.shape[0]} filas, columnas: {list(df.columns[:10])}")

    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    rename_map = {}
    col_set = set(df.columns)

    country_col = next((c for c in col_set if "country" in c and "code" in c), None) or \
                  next((c for c in col_set if "country" in c), None)
    year_col = next((c for c in col_set if c == "year"), None)
    sector_col = next((c for c in col_set if "sector" in c and "code" in c), None) or \
                 next((c for c in col_set if "sector" in c), None)
    pollutant_col = next((c for c in col_set if "pollutant" in c), None) or \
                    next((c for c in col_set if "substance" in c), None)
    value_col = next((c for c in col_set if "emission" in c and ("value" in c or "tonne" in c)), None) or \
                next((c for c in col_set if "value" in c), None)

    if country_col: rename_map[country_col] = "country_code"
    if year_col: rename_map[year_col] = "year"
    if sector_col: rename_map[sector_col] = "sector_code"
    if pollutant_col: rename_map[pollutant_col] = "pollutant"
    if value_col: rename_map[value_col] = "emissions_tonnes"

    df = df.rename(columns=rename_map)

    keep = [c for c in ["country_code", "year", "sector_code", "pollutant", "emissions_tonnes"] if c in df.columns]
    df = df[keep].copy()
    df["emissions_tonnes"] = pd.to_numeric(df.get("emissions_tonnes"), errors="coerce")
    df = df.dropna(subset=["emissions_tonnes"])
    df["year"] = pd.to_numeric(df.get("year"), errors="coerce").astype("Int64")

    out = DATA_PROCESSED / "eea_emissions.parquet"
    df.to_parquet(out, index=False)
    print(f"Guardado: {out} ({len(df):,} filas)")


if __name__ == "__main__":
    build_generation_parquet()
    build_prices_parquet()
    build_eea_parquet()
    print("\nTodos los ficheros Parquet construidos.")
