"""Procesa los rasters PM2.5 interpolados de la EEA (rejilla 1 km, 2019–2024).

Lee:    data/interpolated/.../pm25_avg*.tif  (EPSG:3035, GeoTIFF)
Escribe:
    data/processed/pm25_country_<año>.parquet   — estadísticas por país
    data/processed/pm25_raster_preview_<año>.png — PNG coloreado para Folium
    data/processed/pm25_raster_bounds_<año>.txt  — límites lat/lon para Folium

Pasos:
  1. Estadísticas zonales por polígono NUTS-0 (media, p25, p75, máx.).
  2. Exporta PNG coloreado reproyectado a EPSG:3857 para Folium ImageOverlay.
  3. Guarda estadísticas en Parquet.

Requisitos:
  pip install rasterio rasterstats Pillow branca geopandas pyproj
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import geopandas as gpd

# Soluciona el conflicto de versiones de PROJ entre rasterio y pyproj.
# Debe fijarse ANTES de importar rasterio.
import os
_rasterio_proj = os.path.join(
    os.path.dirname(__import__("rasterio").__file__), "proj_data"
)
if os.path.isdir(_rasterio_proj):
    os.environ["PROJ_DATA"] = _rasterio_proj
    os.environ["PROJ_LIB"] = _rasterio_proj
else:
    import pyproj
    os.environ["PROJ_DATA"] = pyproj.datadir.get_data_dir()

import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.crs import CRS
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from src.config import DATA_GEO, DATA_PROCESSED, FIGURES_DIR, PM25_YEARS

DATA_INTERP = Path(__file__).resolve().parent.parent / "data" / "interpolated"


def find_tif_for_year(year: int) -> Path:
    """Localiza el GeoTIFF de un año dado dentro de data/interpolated/."""
    folder_candidates = list(DATA_INTERP.glob(f"*pm25*_{year}_*"))
    folder_candidates = [p for p in folder_candidates if p.is_dir()]
    if not folder_candidates:
        return None
    folder = folder_candidates[0]
    tifs = list(folder.glob("*.tif"))
    return tifs[0] if tifs else None


# Valores por defecto a nivel de módulo (2019). Se sobrescriben por año en main().
TIF_PATH = find_tif_for_year(2019)
OUT_PARQUET = DATA_PROCESSED / "pm25_country_2019.parquet"
OUT_PNG     = DATA_PROCESSED / "pm25_raster_preview.png"
OUT_BOUNDS  = DATA_PROCESSED / "pm25_raster_bounds.txt"

# El GeoTIFF guarda el CRS como LOCAL_CS["ETRS_1989_LAEA", ...] que rasterio
# no es capaz de interpretar. Según los metadatos de la EEA es EPSG:3035.
RASTER_CRS = "EPSG:3035"


# 1. Estadísticas zonales por país.

def compute_zonal_stats(tif_path: Path = None) -> pd.DataFrame:
    tif_path = tif_path or TIF_PATH
    try:
        from rasterstats import zonal_stats
    except ImportError:
        print("ERROR: rasterstats no instalado. Ejecuta: pip install rasterstats")
        sys.exit(1)

    nuts_path = DATA_GEO / "nuts0.geojson"
    if not nuts_path.exists():
        print(f"ERROR: no se encuentra {nuts_path}. Ejecuta antes 01_download_geo.py.")
        sys.exit(1)

    print("Cargando contornos NUTS-0...")
    nuts = gpd.read_file(nuts_path)

    with rasterio.open(tif_path) as src:
        nodata = src.nodata if src.nodata is not None else -9999
        print(f"  CRS del raster (fichero): {src.crs}  ->  usando {RASTER_CRS}")
        print(f"  nodata: {nodata}")
        print(f"  Tamaño: {src.height}x{src.width}  |  Límites: {src.bounds}")

    # Reproyectamos los NUTS al CRS del raster (EPSG:3035) para estadísticas exactas.
    nuts_reproj = nuts.to_crs(RASTER_CRS)

    print("Calculando estadísticas zonales (puede tardar ~30 s)...")
    stats = zonal_stats(
        nuts_reproj,
        str(tif_path),
        stats=["mean", "min", "max", "percentile_25", "percentile_75", "count"],
        nodata=nodata,
        geojson_out=False,
    )

    df = nuts_reproj[["NUTS_ID"]].copy().reset_index(drop=True)
    df["pm25_mean"] = [s.get("mean") for s in stats]
    df["pm25_min"]  = [s.get("min")  for s in stats]
    df["pm25_max"]  = [s.get("max")  for s in stats]
    df["pm25_p25"]  = [s.get("percentile_25") for s in stats]
    df["pm25_p75"]  = [s.get("percentile_75") for s in stats]
    df["px_count"]  = [s.get("count") for s in stats]
    df["country"]   = df["NUTS_ID"].str[:2]

    # Los NUTS pueden tener varias filas por país (territorios de ultramar, etc.).
    # Nos quedamos con la fila de más píxeles (territorio principal).
    df = df.sort_values("px_count", ascending=False).drop_duplicates("country")
    df = df.reset_index(drop=True)

    print("\nEstadísticas de PM2.5 por país (µg/m³, media anual):")
    print(df[["country", "pm25_mean", "pm25_p25", "pm25_p75"]].sort_values("pm25_mean", ascending=False).to_string(index=False))

    return df


# 2. Exporta PNG coloreado para Folium ImageOverlay.

def export_colorized_png(tif_path: Path = None, out_png: Path = None,
                          out_bounds: Path = None) -> tuple[list, list]:
    """Reproyecta el raster a EPSG:3857 (Web Mercator) y guarda un PNG con transparencia.

    Web Mercator coincide con la proyección de los tiles de Folium/Leaflet, de
    modo que la imagen se alinea pixel a pixel con la rejilla de teselas.
    """
    tif_path = tif_path or TIF_PATH
    out_png = out_png or OUT_PNG
    out_bounds = out_bounds or OUT_BOUNDS
    from rasterio.transform import Affine
    import math

    print("\nExportando PNG coloreado para la capa de Folium...")
    print("  Reproyectando EPSG:3035 -> EPSG:3857 (Web Mercator)...")

    src_crs = CRS.from_epsg(3035)
    dst_crs = CRS.from_epsg(3857)   # Web Mercator — coincide con los tiles de Folium

    with rasterio.open(tif_path) as src:
        nodata = src.nodata if src.nodata is not None else -9999

        # Transform de destino calculado con las dimensiones completas de origen.
        transform_full, width_full, height_full = calculate_default_transform(
            src_crs, dst_crs,
            src.width, src.height,
            *src.bounds,
        )

        # Submuestreo escalando el tamaño de píxel.
        scale_factor = 4
        dst_width  = width_full  // scale_factor
        dst_height = height_full // scale_factor
        dst_transform = transform_full * Affine.scale(scale_factor)

        data_3035 = src.read(1).astype(np.float32)
        data_3035[data_3035 == nodata] = np.nan
        src_transform = src.transform

    reprojected = np.full((dst_height, dst_width), np.nan, dtype=np.float32)
    reproject(
        source=data_3035,
        destination=reprojected,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=nodata,
        dst_nodata=np.nan,
    )
    print(f"  Tamaño tras la reproyección: {dst_height}x{dst_width}")

    # Coloreado con YlOrRd; los nodata pasan a transparente.
    cmap = plt.get_cmap("YlOrRd")
    norm = mcolors.Normalize(vmin=0, vmax=30, clip=True)

    rgba = cmap(norm(reprojected))
    rgba[np.isnan(reprojected), 3] = 0.0

    from PIL import Image
    img = Image.fromarray((rgba * 255).astype(np.uint8), mode="RGBA")
    img.save(out_png, optimize=True)
    print(f"  Guardado: {out_png}  ({img.width}x{img.height} px)")

    # Conversión de límites EPSG:3857 a lat/lon para Folium.
    left_m   = dst_transform.c
    top_m    = dst_transform.f
    right_m  = dst_transform.c + dst_transform.a * dst_width
    bottom_m = dst_transform.f + dst_transform.e * dst_height

    R = 20037508.342789244

    def mercator_to_lon(x_m):
        return x_m / R * 180.0

    def mercator_to_lat(y_m):
        return math.atan(math.exp(y_m * math.pi / R)) * 360.0 / math.pi - 90.0

    lon_min = mercator_to_lon(left_m)
    lon_max = mercator_to_lon(right_m)
    lat_min = mercator_to_lat(bottom_m)
    lat_max = mercator_to_lat(top_m)

    print(f"  Límites 3857 (m): izq={left_m:.0f} inf={bottom_m:.0f} der={right_m:.0f} sup={top_m:.0f}")
    print(f"  Límites WGS84:    SO=[{lat_min:.4f}, {lon_min:.4f}]  NE=[{lat_max:.4f}, {lon_max:.4f}]")

    bounds = [[lat_min, lon_min], [lat_max, lon_max]]
    out_bounds.write_text(str(bounds))
    return bounds


# ── Main ─────────────────────────────────────────────────────────────────────

def process_year(year: int):
    tif = find_tif_for_year(year)
    if tif is None or not tif.exists():
        print(f"  [{year}] GeoTIFF no encontrado — se omite")
        return

    out_parquet = DATA_PROCESSED / f"pm25_country_{year}.parquet"
    out_png     = DATA_PROCESSED / f"pm25_raster_preview_{year}.png"
    out_bounds  = DATA_PROCESSED / f"pm25_raster_bounds_{year}.txt"

    print(f"\n{'='*60}\n  Procesando raster PM2.5 para {year}\n  TIF: {tif.name}\n{'='*60}")
    df = compute_zonal_stats(tif)
    df.to_parquet(out_parquet, index=False)
    print(f"  Guardado: {out_parquet}  ({len(df)} países)")

    export_colorized_png(tif, out_png, out_bounds)
    print(f"  Guardado: {out_png}, {out_bounds}")


def main():
    for year in PM25_YEARS:
        process_year(year)

    # Mantén también los nombres heredados (sin sufijo) apuntando al año 2019.
    legacy_src_png = DATA_PROCESSED / "pm25_raster_preview_2019.png"
    legacy_src_bounds = DATA_PROCESSED / "pm25_raster_bounds_2019.txt"
    if legacy_src_png.exists():
        OUT_PNG.write_bytes(legacy_src_png.read_bytes())
    if legacy_src_bounds.exists():
        OUT_BOUNDS.write_text(legacy_src_bounds.read_text())
    print("\nTodos los años procesados.")


if __name__ == "__main__":
    main()
