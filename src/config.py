from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_GEO = ROOT / "data" / "geo"
DATA_INTERPOLATED = ROOT / "data" / "interpolated"
# data/app: ficheros ligeros pre-agregados que consume la app de Streamlit.
# Es lo único que se sube al repositorio / Streamlit Cloud (unos pocos MB),
# en lugar de los Parquet completos (generation_all.parquet ~173 MB).
DATA_APP = ROOT / "data" / "app"
FIGURES_DIR = ROOT / "report" / "figures"
HTMLS_DIR = ROOT / "htmls"

for d in [DATA_RAW, DATA_PROCESSED, DATA_GEO, DATA_INTERPOLATED, DATA_APP, FIGURES_DIR, HTMLS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HIST_START = "2019-01-01"
HIST_END = "2024-12-31"
# ANALYSIS_YEAR: año más reciente con datos completos (mapas de un solo año).
# COMPARISON_YEAR: año base para mapas de evolución y descarbonización.
ANALYSIS_YEAR = 2024
COMPARISON_YEAR = 2019
PM25_YEARS = [2019, 2020, 2021, 2022, 2023, 2024]

COUNTRIES = [
    "DE", "FR", "ES", "IT", "PL", "NL",
    "BE", "AT", "CZ", "PT", "SE", "NO",
    "FI", "DK", "RO", "HU", "BG", "GR",
    "HR", "SK", "IE", "EE", "LT", "LV",
    "SI", "CH",
]

EMISSION_FACTORS = {
    "Biomass":                            230,
    "Fossil Brown coal/Lignite":         1000,
    "Fossil Coal-derived gas":            490,
    "Fossil Gas":                         490,
    "Fossil Hard coal":                   820,
    "Fossil Oil":                         650,
    "Fossil Oil shale":                   900,
    "Fossil Peat":                        380,
    "Geothermal":                          38,
    "Hydro Pumped Storage":                 0,
    "Hydro Run-of-river and poundage":      0,
    "Hydro Water Reservoir":                0,
    "Marine":                               0,
    "Nuclear":                              0,
    "Other":                              300,
    "Other renewable":                      0,
    "Solar":                                0,
    "Waste":                              330,
    "Wind Offshore":                        0,
    "Wind Onshore":                         0,
}

RENEWABLE_TYPES = {
    "Solar", "Wind Onshore", "Wind Offshore",
    "Hydro Run-of-river and poundage", "Hydro Water Reservoir",
    "Geothermal", "Marine", "Other renewable",
}

# Agrupación de los ~20 tipos de combustible de ENTSO-E en 9 categorías legibles.
# Replica la usada en src/charts.py::plot_generation_mix_comparison para que la
# app y el informe estático muestren la misma paleta y agregación.
FUEL_GROUPS = {
    "Carbón": ["Fossil Brown coal/Lignite", "Fossil Hard coal", "Fossil Coal-derived gas"],
    "Gas": ["Fossil Gas"],
    "Petróleo": ["Fossil Oil", "Fossil Oil shale"],
    "Nuclear": ["Nuclear"],
    "Hidráulica": ["Hydro Run-of-river and poundage", "Hydro Water Reservoir", "Hydro Pumped Storage"],
    "Eólica": ["Wind Onshore", "Wind Offshore"],
    "Solar": ["Solar"],
    "Biomasa": ["Biomass"],
    "Otros": ["Geothermal", "Marine", "Other renewable", "Other", "Waste", "Fossil Peat"],
}

FUEL_GROUP_COLORS = {
    "Carbón": "#4a4a4a", "Gas": "#e74c3c", "Petróleo": "#8b4513", "Nuclear": "#9b59b6",
    "Hidráulica": "#3498db", "Eólica": "#1abc9c", "Solar": "#f1c40f",
    "Biomasa": "#27ae60", "Otros": "#95a5a6",
}

MAP_CRS = "EPSG:3035"
MAP_FIGSIZE = (14, 10)
CHOROPLETH_K = 5
CHOROPLETH_SCHEME = "NaturalBreaks"
CMAP_SEQUENTIAL = "YlOrRd"
CMAP_DIVERGING = "RdYlGn_r"
CMAP_CATEGORICAL = "Set2"

EEA_SECTORS = {
    "1A1a": "Electricidad y calor",
    "1A3b": "Transporte por carretera",
    "1A4b": "Calefacción residencial",
    "1A2":  "Industria",
    "3B":   "Agricultura",
}

COUNTRY_NAMES = {
    "DE": "Alemania", "FR": "Francia", "ES": "España", "IT": "Italia",
    "PL": "Polonia", "NL": "Países Bajos", "BE": "Bélgica", "AT": "Austria",
    "CZ": "Chequia", "PT": "Portugal", "SE": "Suecia", "NO": "Noruega",
    "FI": "Finlandia", "DK": "Dinamarca", "RO": "Rumanía", "HU": "Hungría",
    "BG": "Bulgaria", "GR": "Grecia", "HR": "Croacia", "SK": "Eslovaquia",
    "IE": "Irlanda", "EE": "Estonia", "LT": "Lituania", "LV": "Letonia",
    "SI": "Eslovenia", "CH": "Suiza",
}

# Zonas de oferta cuyos precios día-anterior en ENTSO-E se reportan en moneda
# local en lugar de en EUR.
NON_EUR_PRICE_ZONES = {
    "PL": {2019},
    "RO": {2019, 2020, 2021, 2022},
    "BG": {2019, 2020, 2021, 2022},
}

# Tipos de cambio anuales (BCE) usados para convertir los precios en moneda
# local a EUR.
CURRENCY_TO_EUR = {
    ("PL", 2019): 4.2976,
    ("RO", 2019): 4.7453, ("RO", 2020): 4.8383,
    ("RO", 2021): 4.9215, ("RO", 2022): 4.9315,
    ("BG", 2019): 1.9558, ("BG", 2020): 1.9558,
    ("BG", 2021): 1.9558, ("BG", 2022): 1.9558,
}

NUTS0_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/"
    "geojson/NUTS_RG_10M_2024_4326_LEVL_0.geojson"
)
