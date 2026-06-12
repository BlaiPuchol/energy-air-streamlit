import pandas as pd
import numpy as np
from src.config import EMISSION_FACTORS, RENEWABLE_TYPES, EEA_SECTORS


def compute_carbon_intensity(generation_df: pd.DataFrame) -> pd.DataFrame:
    df = generation_df.copy()

    total_gen = pd.Series(0.0, index=df.index)
    total_emissions = pd.Series(0.0, index=df.index)
    renewable_gen = pd.Series(0.0, index=df.index)

    for col in df.columns:
        if col in EMISSION_FACTORS:
            gen = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)
            total_gen += gen
            total_emissions += gen * EMISSION_FACTORS[col]
            if col in RENEWABLE_TYPES:
                renewable_gen += gen

    df["total_generation_mw"] = total_gen
    df["total_emissions_gco2"] = total_emissions
    df["carbon_intensity_gco2_kwh"] = np.where(
        total_gen > 0, total_emissions / total_gen, np.nan
    )
    df["renewable_share"] = np.where(
        total_gen > 0, renewable_gen / total_gen, np.nan
    )
    return df


def aggregate_to_country_year(generation_df: pd.DataFrame) -> pd.DataFrame:
    df = generation_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df["year"] = df.index.year

    agg = df.groupby(["country", "year"]).agg(
        carbon_intensity_mean=("carbon_intensity_gco2_kwh", "mean"),
        renewable_share_mean=("renewable_share", "mean"),
        total_generation_gwh=("total_generation_mw", lambda x: x.sum() / 1000),
    ).reset_index()
    return agg


def aggregate_to_country_month(generation_df: pd.DataFrame) -> pd.DataFrame:
    df = generation_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df["year"] = df.index.year
    df["month"] = df.index.month

    agg = df.groupby(["country", "year", "month"]).agg(
        carbon_intensity_mean=("carbon_intensity_gco2_kwh", "mean"),
        renewable_share_mean=("renewable_share", "mean"),
    ).reset_index()
    return agg


def rank_dominant_sector(eea_df: pd.DataFrame, pollutant: str = "PM2.5",
                          year: int = 2022) -> pd.DataFrame:
    df = eea_df[
        (eea_df["pollutant"] == pollutant) &
        (eea_df["year"] == year) &
        (eea_df["sector_code"].isin(EEA_SECTORS.keys()))
    ].copy()

    if df.empty:
        return pd.DataFrame(columns=["country_code", "sector_name", "emissions_tonnes"])

    df["sector_name"] = df["sector_code"].map(EEA_SECTORS)
    idx = df.groupby("country_code")["emissions_tonnes"].idxmax()
    dominant = df.loc[idx, ["country_code", "sector_name", "emissions_tonnes"]]
    return dominant.reset_index(drop=True)


def compute_sector_shares(eea_df: pd.DataFrame, pollutant: str = "PM2.5",
                          year: int = 2022) -> pd.DataFrame:
    """Calcula la cuota sectorial (%) por país para un contaminante y año."""
    df = eea_df[
        (eea_df["pollutant"] == pollutant) &
        (eea_df["year"] == year) &
        (eea_df["sector_code"].isin(EEA_SECTORS.keys()))
    ].copy()

    if df.empty:
        return pd.DataFrame()

    df["sector_name"] = df["sector_code"].map(EEA_SECTORS)
    totals = df.groupby("country_code")["emissions_tonnes"].sum().rename("total")
    df = df.merge(totals, on="country_code")
    df["share_pct"] = (df["emissions_tonnes"] / df["total"] * 100).round(1)

    pivot = df.pivot_table(
        index="country_code", columns="sector_name",
        values="share_pct", aggfunc="first",
    ).reset_index()
    pivot.columns.name = None
    return pivot


def compute_decoupling_rate(country_year_df: pd.DataFrame,
                             start_year: int = 2019,
                             end_year: int = 2023) -> pd.DataFrame:
    start = country_year_df[country_year_df["year"] == start_year].set_index("country")
    end = country_year_df[country_year_df["year"] == end_year].set_index("country")

    common = start.index.intersection(end.index)
    change = pd.DataFrame({
        "carbon_intensity_start": start.loc[common, "carbon_intensity_mean"],
        "carbon_intensity_end": end.loc[common, "carbon_intensity_mean"],
    })
    change["pct_change"] = (
        (change["carbon_intensity_end"] - change["carbon_intensity_start"])
        / change["carbon_intensity_start"]
    ) * 100
    return change.reset_index().rename(columns={"index": "country"})


def aggregate_openaq_to_country(openaq_df: pd.DataFrame) -> pd.DataFrame:
    pm25 = (
        openaq_df[openaq_df["parameter"] == "pm25"]
        .groupby("country")["last_value"]
        .mean()
        .reset_index()
        .rename(columns={"last_value": "pm25_mean"})
    )
    no2 = (
        openaq_df[openaq_df["parameter"] == "no2"]
        .groupby("country")["last_value"]
        .mean()
        .reset_index()
        .rename(columns={"last_value": "no2_mean"})
    )
    return pm25.merge(no2, on="country", how="outer")
