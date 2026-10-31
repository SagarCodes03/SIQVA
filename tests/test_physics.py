"""Verification Test Suite for Ocean Physics Features:
Test 1: Bay of Bengal Temperature Inversion & Barrier Layer
Test 2: Contiguous Upper-Layer TCHP Integration
Test 3: Shallow vs Deep Acoustic Profile (SOFAR Check)
Test 4: Live argopy Smoke Test & Plotly Chart Generation
"""

from __future__ import annotations

import json
import gsw
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from siqva.physics import (
    ACOUSTIC_DISCLAIMER,
    CYCLONE_TCHP_DISCLAIMER,
    THERMOCLINE_DISCLAIMER,
    build_feature_context,
    compute_new_features,
)
from siqva.plots import (
    plot_acoustic_profile,
    plot_cyclone_tchp,
    plot_thermocline_and_barrier,
)
from siqva.rules_parser import parse_rules
from siqva.spec import Intent, Variable


def test_1_bay_of_bengal_inversion_and_barrier_layer():
    """Test 1 — Bay of Bengal Temperature Inversion & Barrier Layer.

    Synthetic profile where salinity jumps at 25 m (causing density MLD around 25 m)
    while a subsurface temperature inversion occurs at 30 m before cooling
    below T_10m - 0.2°C at 55 m.
    Verify:
    - mld_dens_m < ild_temp_m
    - barrier_layer_m is positive (~30 m)
    - z20_isotherm_m accurately finds the first downward crossing despite the inversion.
    """
    z = np.linspace(0.0, 300.0, 301)
    lat = 15.0  # Bay of Bengal latitude
    lon = 90.0
    pres = gsw.p_from_z(-z, lat)

    # Salinity: Fresh BoB river plume at surface (31.0 PSU), jumping at 25 m to 34.2 PSU
    psal = np.where(z < 25.0, 31.0, 34.2)

    # Temperature:
    # 0-10 m: 29.0°C (T_10m = 29.0°C)
    # 10-30 m: warming to 29.8°C (subsurface temperature inversion)
    # 30-55 m: cooling from 29.8°C to 28.8°C (T_10m - 0.2°C reached at 55 m)
    # 55-100 m: cooling to 20.0°C (Z20 reached at 100 m)
    # 100-300 m: cooling to 12.0°C
    temp = np.zeros_like(z)
    for i, depth in enumerate(z):
        if depth <= 10.0:
            temp[i] = 29.0
        elif depth <= 30.0:
            temp[i] = 29.0 + (depth - 10.0) / 20.0 * 0.8
        elif depth <= 55.0:
            temp[i] = 29.8 - (depth - 30.0) / 25.0 * 1.0
        elif depth <= 100.0:
            temp[i] = 28.8 - (depth - 55.0) / 45.0 * 8.8
        else:
            temp[i] = 20.0 - (depth - 100.0) / 200.0 * 8.0

    df = pd.DataFrame({
        "wmo_id": "TEST_BOB_01",
        "cycle": 1,
        "time": "2024-05-15 12:00:00",
        "lat": lat,
        "lon": lon,
        "pres": pres,
        "temp": temp,
        "psal": psal,
    })

    enriched_df, summaries = compute_new_features(df)
    assert len(summaries) == 1
    s = summaries[0]

    # Verify density MLD is shallow (~25 m) due to strong halocline
    assert s["mld_dens_m"] is not None
    assert 24.0 <= s["mld_dens_m"] <= 26.0

    # Verify ILD is deeper (~55 m) due to temperature inversion
    assert s["ild_temp_m"] is not None
    assert 54.0 <= s["ild_temp_m"] <= 56.0

    # Verify positive Barrier Layer (~30 m)
    assert s["barrier_layer_m"] is not None
    assert s["barrier_layer_m"] > 0
    assert 29.0 <= s["barrier_layer_m"] <= 31.0

    # Verify Z20 isotherm accurately identified at 100 m
    assert s["z20_isotherm_m"] is not None
    assert abs(s["z20_isotherm_m"] - 100.0) < 0.5

    # Verify thermocline chart generation
    fig = plot_thermocline_and_barrier(enriched_df, s)
    assert isinstance(fig, go.Figure)


def test_2_contiguous_upper_layer_tchp_integration():
    """Test 2 — Contiguous Upper-Layer TCHP Integration:

    Deep Warm Inversion Layer must NOT be included if separated by cooler water < 26°C.
    """
    z = np.linspace(0.0, 200.0, 201)
    lat, lon = 15.0, 65.0  # Arabian Sea
    pres = gsw.p_from_z(-z, lat)
    psal = np.full_like(z, 36.0)

    # Temperature profile:
    # 0-60m: >26°C (30.0°C cooling to 26.0°C at exactly 60m)
    # 60-110m: cools from 26.0°C to 22.0°C
    # 110-150m: warm inversion rising back to 27.0°C (deep warm core)
    # 150-200m: cools to 16.0°C
    temp = np.zeros_like(z)
    for i, depth in enumerate(z):
        if depth <= 60.0:
            temp[i] = 30.0 - (depth / 60.0) * 4.0
        elif depth <= 110.0:
            temp[i] = 26.0 - ((depth - 60.0) / 50.0) * 4.0
        elif depth <= 150.0:
            temp[i] = 22.0 + np.sin((depth - 110.0) / 40.0 * np.pi) * 5.0
        else:
            temp[i] = 22.0 - ((depth - 150.0) / 50.0) * 6.0

    df = pd.DataFrame({
        "wmo_id": "TEST_TCHP_02",
        "cycle": 1,
        "time": "2024-05-15 12:00:00",
        "lat": lat,
        "lon": lon,
        "pres": pres,
        "temp": temp,
        "psal": psal,
    })

    enriched_df, summaries = compute_new_features(df)
    assert len(summaries) == 1
    s = summaries[0]

    # Verify z26_isotherm_m is exactly 60.0 m
    assert s["z26_isotherm_m"] is not None
    assert abs(s["z26_isotherm_m"] - 60.0) < 0.2

    # Verify TCHP is positive
    assert s["tchp_kj_cm2"] > 0.0

    # Manually integrate strictly from 0 to 60 m to verify contiguous layer integration
    dens = enriched_df["rho"].to_numpy(dtype=float)
    cp0 = 3991.86795711963
    trapz_func = getattr(np, "trapezoid", getattr(np, "trapz", None))
    sub_60 = z <= 60.0
    expected_heat = float(trapz_func(dens[sub_60] * cp0 * (temp[sub_60] - 26.0), z[sub_60]))
    expected_tchp = round(max(0.0, expected_heat / 1e7), 1)

    assert s["tchp_kj_cm2"] == expected_tchp

    # Verify that if the deep inversion at 120m was mistakenly included, TCHP would be higher
    mask_warm_all = temp > 26.0
    naive_heat = float(trapz_func(dens[mask_warm_all] * cp0 * (temp[mask_warm_all] - 26.0), z[mask_warm_all]))
    naive_tchp = round(naive_heat / 1e7, 1)
    assert naive_tchp > s["tchp_kj_cm2"]

    # Verify cyclone chart generation & polygon clipping
    fig = plot_cyclone_tchp(enriched_df, s)
    assert isinstance(fig, go.Figure)

    # Verify edge case: brief cooler dip (25.8°C) above Z26 does not cross left of 26°C line
    df_dip = enriched_df.copy()
    df_dip.loc[df_dip["depth_m"] == 10.0, "temp"] = 25.8
    fig_dip = plot_cyclone_tchp(df_dip, s)
    poly_trace = next(tr for tr in fig_dip.data if "TCHP Integrated Area" in tr.name)
    assert np.all(np.array(poly_trace.x) >= 26.0), "TCHP shaded polygon crossed left of 26°C isotherm"


def test_3_acoustic_shallow_vs_deep_profile():
    """Test 3 — Shallow vs Deep Acoustic Profile (SOFAR Check):

    - Run a shallow profile (max_depth_m = 500m) and assert sofar_axis_m is None while sld_m is not None.
    - Run a deep profile (max_depth_m = 1800m) and assert sofar_axis_m is not None.
    """
    lat, lon = 10.0, 65.0

    # Shallow Profile: 5 m to 500 m
    z_shallow = np.linspace(5.0, 500.0, 100)
    p_shallow = gsw.p_from_z(-z_shallow, lat)
    t_shallow = 28.0 - (z_shallow / 500.0) * 18.0
    s_shallow = np.full_like(z_shallow, 35.5)

    df_shallow = pd.DataFrame({
        "wmo_id": "SHALLOW_FLOAT",
        "cycle": 1,
        "time": "2024-05-15 12:00:00",
        "lat": lat,
        "lon": lon,
        "pres": p_shallow,
        "temp": t_shallow,
        "psal": s_shallow,
    })

    enriched_shallow, sum_shallow = compute_new_features(df_shallow)
    assert len(sum_shallow) == 1
    s_shal = sum_shallow[0]
    assert s_shal["max_depth_m"] < 1000.0
    assert s_shal["sofar_axis_m"] is None, "SOFAR axis must be None for profiles < 1000 m"
    assert s_shal["sld_m"] is not None, "SLD should be computed for shallow profile"

    # Deep Profile: 5 m to 1800 m
    z_deep = np.linspace(5.0, 1800.0, 360)
    p_deep = gsw.p_from_z(-z_deep, lat)
    t_deep = 2.0 + 26.0 * np.exp(-z_deep / 350.0)
    s_deep = 34.8 + 0.7 * np.exp(-z_deep / 250.0)

    df_deep = pd.DataFrame({
        "wmo_id": "DEEP_FLOAT",
        "cycle": 1,
        "time": "2024-05-15 12:00:00",
        "lat": lat,
        "lon": lon,
        "pres": p_deep,
        "temp": t_deep,
        "psal": s_deep,
    })

    enriched_deep, sum_deep = compute_new_features(df_deep)
    assert len(sum_deep) == 1
    s_dp = sum_deep[0]
    assert s_dp["max_depth_m"] >= 1000.0
    assert s_dp["sofar_axis_m"] is not None, "SOFAR axis must NOT be None for profiles >= 1000 m"
    assert s_dp["sld_m"] is not None
    assert s_dp["sofar_axis_m"] > s_dp["sld_m"]

    fig_shal = plot_acoustic_profile(enriched_shallow, s_shal)
    fig_deep = plot_acoustic_profile(enriched_deep, s_dp)
    assert isinstance(fig_shal, go.Figure)
    assert isinstance(fig_deep, go.Figure)


@pytest.mark.network
def test_4_live_argopy_smoke_test():
    """Test 4 — Live argopy Smoke Test:

    Fetch 1 real float from the Arabian Sea or Bay of Bengal via argopy,
    filter for QC flags 1 & 2, run compute_new_features(),
    generate all 3 Plotly figures in plots.py,
    and verify the resulting summary and disclaimers.
    """
    try:
        import argopy
        fetcher = argopy.DataFetcher(src="erddap").profile(2902264, 1)
        ds = fetcher.to_dataframe()
    except Exception as e:
        pytest.skip(f"Live argopy fetch failed (network or server unavailable): {e}")

    assert not ds.empty, "Fetched Argo profile DataFrame is empty"

    qc_mask = ds["PRES_QC"].isin([1, 2]) & ds["TEMP_QC"].isin([1, 2]) & ds["PSAL_QC"].isin([1, 2])
    ds_filtered = ds[qc_mask].copy()
    assert not ds_filtered.empty, "No data remaining after QC flag filtering"

    df_argo = ds_filtered.rename(
        columns={
            "PLATFORM_NUMBER": "wmo_id",
            "CYCLE_NUMBER": "cycle",
            "TIME": "time",
            "LATITUDE": "lat",
            "LONGITUDE": "lon",
            "PRES": "pres",
            "TEMP": "temp",
            "PSAL": "psal",
        }
    )[["wmo_id", "cycle", "time", "lat", "lon", "pres", "temp", "psal"]]

    enriched_df, summaries = compute_new_features(df_argo)
    assert len(summaries) >= 1, "Expected at least 1 profile summary"

    summary = summaries[0]

    fig_therm = plot_thermocline_and_barrier(enriched_df, summary)
    fig_cyclone = plot_cyclone_tchp(enriched_df, summary)
    fig_acoustic = plot_acoustic_profile(enriched_df, summary)

    assert isinstance(fig_therm, go.Figure)
    assert isinstance(fig_cyclone, go.Figure)
    assert isinstance(fig_acoustic, go.Figure)

    ctx_therm = build_feature_context("thermocline_mld", summaries)
    assert "Z20" in ctx_therm
    assert "commercial fish-catch" in ctx_therm

    ctx_tchp = build_feature_context("cyclone_tchp", summaries)
    assert "Leipper & Volgenau" in ctx_tchp
    assert "Mainelli et al." in ctx_tchp

    ctx_acoust = build_feature_context("acoustic_profile", summaries)
    assert "SOFAR" in ctx_acoust
    assert "1000" in ctx_acoust


def test_physics_intents_and_variable_auto_inclusion():
    """Verify natural language rules parser maps physics queries to Intent enums and auto-includes variables."""
    r_therm = parse_rules("thermocline and barrier layer in Bay of Bengal between 2022-04-01 and 2022-04-15")
    assert r_therm.intent == Intent.THERMOCLINE
    assert set(r_therm.variables) == {Variable.PRES, Variable.PSAL, Variable.TEMP}
    assert "variables" not in r_therm.missing

    r_tchp = parse_rules("cyclone heat potential tchp in Arabian Sea in May 2022")
    assert r_tchp.intent == Intent.TCHP
    assert set(r_tchp.variables) == {Variable.PRES, Variable.PSAL, Variable.TEMP}
    assert "variables" not in r_tchp.missing

    r_ac = parse_rules("acoustic sound speed profile in Arabian Sea between 2022-01-01 and 2022-01-10")
    assert r_ac.intent == Intent.ACOUSTIC
    assert set(r_ac.variables) == {Variable.PRES, Variable.PSAL, Variable.TEMP}
    assert "variables" not in r_ac.missing
