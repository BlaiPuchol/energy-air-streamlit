"""Descarga emisiones sectoriales de contaminantes (Eurostat env_air_emis).

Agrega los subcódigos NFR a los cinco sectores EEA usados en el proyecto.
Guarda data/raw/eea_emissions.csv con las columnas:
  country_code, year, sector_code, pollutant, emissions_tonnes
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import pandas as pd
from src.config import DATA_RAW, COUNTRIES

OUT_PATH = DATA_RAW / "eea_emissions.csv"

if OUT_PATH.exists():
    print(f"Ya existe: {OUT_PATH}")
    raise SystemExit(0)

# Subcódigos NFR → código de sector EEA principal.
NFR_TO_SECTOR = {}
for code in ["NFR1A1A"]:
    NFR_TO_SECTOR[code] = "1A1a"
for code in ["NFR1A3B1", "NFR1A3B2", "NFR1A3B3", "NFR1A3B4",
             "NFR1A3B5", "NFR1A3B6", "NFR1A3B7"]:
    NFR_TO_SECTOR[code] = "1A3b"
for code in ["NFR1A4B1", "NFR1A4B2"]:
    NFR_TO_SECTOR[code] = "1A4b"
for code in ["NFR1A2A", "NFR1A2B", "NFR1A2C", "NFR1A2D",
             "NFR1A2E", "NFR1A2F", "NFR1A2G7", "NFR1A2G8"]:
    NFR_TO_SECTOR[code] = "1A2"
for code in ["NFR3B1A", "NFR3B1B", "NFR3B2", "NFR3B3", "NFR3B4A",
             "NFR3B4D", "NFR3B4E", "NFR3B4F", "NFR3B4G1", "NFR3B4G2",
             "NFR3B4G3", "NFR3B4G4", "NFR3B4H"]:
    NFR_TO_SECTOR[code] = "3B"

TARGET_NFR = list(NFR_TO_SECTOR.keys())

# Contaminantes: códigos airpol de Eurostat.
POLLUTANTS = {
    "PM2.5": "PM2_5",
    "NOx":   "NOX",
    "NH3":   "NH3",
    "SO2":   "SOX",
}

BASE_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
    "env_air_emis?format=JSON&lang=en"
)


def fetch_bulk(airpol_code: str) -> pd.DataFrame:
    """Descarga todos los países × sectores × años para un contaminante."""
    geo_filter = "&".join(f"geo={c}" for c in COUNTRIES)
    nfr_filter = "&".join(f"src_nfr={n}" for n in TARGET_NFR)
    url = f"{BASE_URL}&airpol={airpol_code}&{geo_filter}&{nfr_filter}"

    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    dim_ids   = data.get("id", [])
    dim_sizes = data.get("size", [])
    dims      = data["dimension"]
    values    = data.get("value", {})

    if not values:
        return pd.DataFrame()

    # Listas ordenadas por dimensión.
    def _ordered_keys(dim_name):
        return list(dims[dim_name]["category"]["index"].keys())

    ordered = {name: _ordered_keys(name) for name in dim_ids}
    sizes   = dict(zip(dim_ids, dim_sizes))

    records = []
    for flat_str, val in values.items():
        flat = int(flat_str)
        # Decodifica el índice plano a índices por dimensión.
        coord = {}
        rem = flat
        for dim in reversed(dim_ids):
            s = sizes[dim]
            if s == 0:
                coord[dim] = None
                continue
            coord[dim] = rem % s
            rem //= s

        geo_code = ordered["geo"][coord["geo"]] if coord.get("geo") is not None else None
        nfr_code = ordered["src_nfr"][coord["src_nfr"]] if coord.get("src_nfr") is not None else None
        year_str = ordered["time"][coord["time"]] if coord.get("time") is not None else None

        if geo_code not in COUNTRIES or nfr_code not in NFR_TO_SECTOR:
            continue
        try:
            year = int(year_str)
        except (TypeError, ValueError):
            continue

        records.append({
            "country_code": geo_code,
            "year": year,
            "nfr_code": nfr_code,
            "sector_code": NFR_TO_SECTOR[nfr_code],
            "emissions_kt": val,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Agrega los subcódigos al sector.
    agg = (
        df.groupby(["country_code", "year", "sector_code"])["emissions_kt"]
        .sum()
        .reset_index()
    )
    agg["emissions_tonnes"] = agg["emissions_kt"] * 1000
    return agg[["country_code", "year", "sector_code", "emissions_tonnes"]]


all_dfs = []
for pollutant_name, eurostat_code in POLLUTANTS.items():
    print(f"Descargando {pollutant_name} ({eurostat_code})...")
    try:
        df = fetch_bulk(eurostat_code)
        if df.empty:
            print("  Sin datos.")
        else:
            df["pollutant"] = pollutant_name
            all_dfs.append(df)
            print(f"  {len(df):,} filas")
    except Exception as e:
        print(f"  FALLÓ: {e}")

if not all_dfs:
    print("\nTodas las descargas han fallado.")
    raise SystemExit(1)

combined = pd.concat(all_dfs, ignore_index=True)
combined = combined.dropna(subset=["emissions_tonnes"])
combined["emissions_tonnes"] = pd.to_numeric(combined["emissions_tonnes"], errors="coerce")
combined = combined.dropna()

combined.to_csv(OUT_PATH, index=False)
print(f"\nGuardado: {OUT_PATH} ({len(combined):,} filas)")
