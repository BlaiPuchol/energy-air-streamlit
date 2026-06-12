"""Descarga el GeoJSON NUTS-0 (países) de Eurostat. Rápido; ejecutar primero."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from src.config import DATA_GEO, NUTS0_URL

OUT_PATH = DATA_GEO / "nuts0.geojson"

if OUT_PATH.exists():
    print(f"Ya existe: {OUT_PATH}")
    raise SystemExit(0)

print("Descargando NUTS-0 GeoJSON desde Eurostat GISCO...")
print(f"  URL: {NUTS0_URL}")

try:
    resp = requests.get(NUTS0_URL, timeout=120)
    resp.raise_for_status()
    with open(OUT_PATH, "wb") as f:
        f.write(resp.content)
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Guardado: {OUT_PATH} ({size_kb:.0f} KB)")
except Exception as e:
    print(f"Falló: {e}")
    print("Descarga manual desde:")
    print("  https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units/countries")
    print("  Selecciona NUTS 2024, escala 1:10M, formato GeoJSON, EPSG:4326")
    print(f"  Guárdalo como: {OUT_PATH}")
