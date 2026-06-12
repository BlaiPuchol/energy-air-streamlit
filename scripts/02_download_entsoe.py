"""Descarga histórica ENTSO-E: generación y precios día-anterior por país.

Ejecutar una sola vez. Puede tardar varias horas. Escribe CSV en data/raw/.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from entsoe import EntsoePandasClient
import pandas as pd
from dotenv import load_dotenv
import os
import time

from src.config import COUNTRIES, DATA_RAW, HIST_START, HIST_END

# entsoe-py rechaza códigos ISO simples para países divididos en zonas de oferta.
# Descargamos cada zona y las guardamos lado a lado para agregarlas después.
PRICE_ZONES = {
    "DE": ["DE_LU"],
    "IT": ["IT_NORD", "IT_CNOR", "IT_CSUD", "IT_SUD",
           "IT_SICI", "IT_SARD", "IT_CALA"],
    "NO": ["NO_1", "NO_2", "NO_3", "NO_4", "NO_5"],
    "SE": ["SE_1", "SE_2", "SE_3", "SE_4"],
    "DK": ["DK_1", "DK_2"],
}

load_dotenv()
client = EntsoePandasClient(api_key=os.getenv("ENTSOE_API_KEY"))

start = pd.Timestamp(HIST_START, tz="Europe/Brussels")
end = pd.Timestamp(HIST_END, tz="Europe/Brussels")


def download_yearly(fn, country, label):
    dfs = []
    for year in range(start.year, end.year + 1):
        y_start = pd.Timestamp(f"{year}-01-01", tz="Europe/Brussels")
        y_end = pd.Timestamp(f"{year + 1}-01-01", tz="Europe/Brussels")
        y_start = max(y_start, start)
        y_end = min(y_end, end)
        try:
            df = fn(country, start=y_start, end=y_end)
            dfs.append(df)
            print(f"  {year}: {len(df)} filas")
        except Exception as e:
            print(f"  {year}: FALLÓ — {e}")
        time.sleep(2)
    return dfs


for country in COUNTRIES:
    print(f"\n{'='*60}\n{country}\n{'='*60}")

    gen_path = DATA_RAW / f"generation_{country}.csv"
    if gen_path.exists():
        print("  Generación ya descargada, se omite.")
    else:
        try:
            dfs = download_yearly(client.query_generation, country, "generation")
            if dfs:
                pd.concat(dfs).to_csv(gen_path)
                print(f"  Guardado: {gen_path}")
        except Exception as e:
            print(f"  Generación FALLÓ: {e}")
    time.sleep(3)

    price_path = DATA_RAW / f"prices_{country}.csv"
    if price_path.exists():
        print("  Precios ya descargados, se omite.")
    else:
        zones = PRICE_ZONES.get(country, [country])
        if zones != [country]:
            print(f"  País dividido en zonas de oferta: {zones}")
        zone_series = {}
        for zone in zones:
            print(f"  Zona {zone}:")
            try:
                dfs = download_yearly(client.query_day_ahead_prices, zone, "prices")
                if dfs:
                    zone_series[zone] = pd.concat(dfs)
            except Exception as e:
                print(f"  Zona {zone} FALLÓ: {e}")
            time.sleep(2)
        if zone_series:
            wide = pd.concat(zone_series, axis=1)
            wide.columns = list(zone_series.keys())
            wide.to_csv(price_path)
            print(f"  Guardado: {price_path} (columnas: {list(wide.columns)})")
    time.sleep(3)

print("\nHecho.")
