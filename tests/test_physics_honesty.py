"""Tests for physics honesty: SOFAR axis interior requirement, SLD surface behavior, and aggregate feature reporting."""

from __future__ import annotations

import gsw
import numpy as np
import pandas as pd
import pytest

from siqva.analyzer import analyze
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.physics import (
    MIN_SAMPLES_EACH_SIDE,
    build_feature_context,
    compute_new_features,
)
from siqva.spec import DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable


def test_sofar_interior_minimum_near_1000m_is_found():
    """A profile with a true interior sound-speed minimum must report the interior axis."""
    lat, lon = 15.0, 65.0
    z = np.linspace(5.0, 1800.0, 360)
    p = gsw.p_from_z(-z, lat)
    # Temperature drops to 2C, exponential decay creates interior sound speed minimum near 1000m
    t = 2.0 + 26.0 * np.exp(-z / 350.0)
    s = 34.8 + 0.7 * np.exp(-z / 250.0)

    df = pd.DataFrame({
        "PLATFORM_NUMBER": [1001] * len(z),
        "CYCLE_NUMBER": [1] * len(z),
        "LATITUDE": [lat] * len(z),
        "LONGITUDE": [lon] * len(z),
        "TIME": ["2024-05-15"] * len(z),
        "PRES": p,
        "TEMP": t,
        "PSAL": s,
    })

    _, summaries = compute_new_features(df, intent=Intent.ACOUSTIC)
    assert len(summaries) == 1
    s_res = summaries[0]

    assert s_res.sofar_axis_m is not None
    # Verify it is an interior point near 1000 m
    assert 900.0 <= s_res.sofar_axis_m <= 1100.0
    assert s_res.sofar_status == f"{s_res.sofar_axis_m:.1f} m"
    # Never the deepest point
    assert s_res.sofar_axis_m < s_res.max_depth_m - 50.0


def test_sofar_monotonic_profile_is_not_reached():
    """A monotonic sound speed profile must never report the deepest sample as the SOFAR axis."""
    lat, lon = 60.0, -30.0
    z = np.linspace(5.0, 1500.0, 150)
    p = gsw.p_from_z(-z, lat)
    # Strong cooling down to the bottom ensures sound speed strictly decreases monotonically
    t = np.linspace(10.0, -1.0, 150)
    s = np.full_like(z, 35.0)

    df = pd.DataFrame({
        "PLATFORM_NUMBER": [1002] * len(z),
        "CYCLE_NUMBER": [1] * len(z),
        "LATITUDE": [lat] * len(z),
        "LONGITUDE": [lon] * len(z),
        "TIME": ["2024-05-15"] * len(z),
        "PRES": p,
        "TEMP": t,
        "PSAL": s,
    })

    _, summaries = compute_new_features(df, intent=Intent.ACOUSTIC)
    assert len(summaries) == 1
    s_res = summaries[0]

    # Deepest sample must NEVER be reported as SOFAR axis
    assert s_res.sofar_axis_m is None
    assert s_res.sofar_status is not None
    assert "SOFAR axis not reached" in s_res.sofar_status


def test_sofar_shallow_500dbar_profile_is_not_reached():
    """Profiles < 1000 m must report not reached due to depth."""
    lat, lon = 15.0, 65.0
    z = np.linspace(5.0, 500.0, 100)
    p = gsw.p_from_z(-z, lat)
    t = np.linspace(28.0, 12.0, 100)
    s = np.full_like(z, 35.5)

    df = pd.DataFrame({
        "PLATFORM_NUMBER": [1003] * len(z),
        "CYCLE_NUMBER": [1] * len(z),
        "LATITUDE": [lat] * len(z),
        "LONGITUDE": [lon] * len(z),
        "TIME": ["2024-05-15"] * len(z),
        "PRES": p,
        "TEMP": t,
        "PSAL": s,
    })

    _, summaries = compute_new_features(df, intent=Intent.ACOUSTIC)
    assert len(summaries) == 1
    s_res = summaries[0]

    assert s_res.sofar_axis_m is None
    assert "SOFAR axis not reached: profile ends at" in s_res.sofar_status


def test_sld_surface_maximum_vs_subsurface_duct():
    """SLD at the shallowest sample must be recognized as sound speed maximum at the surface."""
    lat, lon = 15.0, 65.0

    # Case 1: Surface maximum (warmest at surface, decreasing downwards)
    z1 = np.linspace(5.0, 300.0, 60)
    p1 = gsw.p_from_z(-z1, lat)
    t1 = np.linspace(28.0, 15.0, 60)
    s1 = np.full_like(z1, 35.0)

    df1 = pd.DataFrame({
        "PLATFORM_NUMBER": [2001] * len(z1),
        "CYCLE_NUMBER": [1] * len(z1),
        "LATITUDE": [lat] * len(z1),
        "LONGITUDE": [lon] * len(z1),
        "TIME": ["2024-05-15"] * len(z1),
        "PRES": p1,
        "TEMP": t1,
        "PSAL": s1,
    })

    _, sum1 = compute_new_features(df1, intent=Intent.ACOUSTIC)
    s1_res = sum1[0]
    assert s1_res.sld_is_surface is True
    assert "sound speed maximum at the surface" in s1_res.sld_status

    ctx1 = build_feature_context("acoustic", [s1_res])
    assert "sound speed maximum at the surface" in ctx1

    # Case 2: Subsurface duct (isothermal layer from 0 to 50m where pressure increases sound speed)
    z2 = np.linspace(5.0, 300.0, 60)
    p2 = gsw.p_from_z(-z2, lat)
    # Isothermal 28.0C down to 50m, then sharp thermocline
    t2 = np.where(z2 <= 50.0, 28.0, 28.0 - (z2 - 50.0) * 0.1)
    s2 = np.full_like(z2, 35.0)

    df2 = pd.DataFrame({
        "PLATFORM_NUMBER": [2002] * len(z2),
        "CYCLE_NUMBER": [1] * len(z2),
        "LATITUDE": [lat] * len(z2),
        "LONGITUDE": [lon] * len(z2),
        "TIME": ["2024-05-15"] * len(z2),
        "PRES": p2,
        "TEMP": t2,
        "PSAL": s2,
    })

    _, sum2 = compute_new_features(df2, intent=Intent.ACOUSTIC)
    s2_res = sum2[0]
    assert s2_res.sld_is_surface is False
    assert s2_res.sld_m is not None
    # Maximum should be near 50 m due to pressure increase in isothermal layer
    assert 40.0 <= s2_res.sld_m <= 60.0


def test_aggregate_text_and_missing_data_notes():
    """Analysis summary must include 'N of M profiles reached the feature' and count shallower profiles."""
    lat, lon = 15.0, 65.0

    # Profile 1: reaches 2000 dbar, reaches Z20, Z26, SOFAR
    z1 = np.linspace(5.0, 1900.0, 200)
    p1 = gsw.p_from_z(-z1, lat)
    t1 = 2.0 + 26.0 * np.exp(-z1 / 350.0)
    s1 = 34.8 + 0.7 * np.exp(-z1 / 250.0)
    df1 = pd.DataFrame({
        "PLATFORM_NUMBER": [3001] * len(z1),
        "CYCLE_NUMBER": [1] * len(z1),
        "LATITUDE": [lat] * len(z1),
        "LONGITUDE": [lon] * len(z1),
        "TIME": ["2024-05-15"] * len(z1),
        "PRES": p1,
        "TEMP": t1,
        "PSAL": s1,
    })

    # Profile 2: shallow (400 dbar), cold (never reaches 20C or 26C, no SOFAR)
    z2 = np.linspace(5.0, 400.0, 50)
    p2 = gsw.p_from_z(-z2, lat)
    t2 = np.linspace(15.0, 4.0, 50)
    s2 = np.full_like(z2, 35.0)
    df2 = pd.DataFrame({
        "PLATFORM_NUMBER": [3002] * len(z2),
        "CYCLE_NUMBER": [1] * len(z2),
        "LATITUDE": [lat] * len(z2),
        "LONGITUDE": [lon] * len(z2),
        "TIME": ["2024-05-15"] * len(z2),
        "PRES": p2,
        "TEMP": t2,
        "PSAL": s2,
    })

    combined = pd.concat([df1, df2], ignore_index=True)

    spec = QuerySpec(
        region=[lon - 1, lon + 1, lat - 1, lat + 1],
        date_range=DateRange(start="2024-05-01", end="2024-05-31"),
        variables=[Variable.TEMP, Variable.PSAL, Variable.PRES],
        depth_range=DepthRange(min_depth=0.0, max_depth=2000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.ACOUSTIC,
    )

    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=combined,
        is_cached=True,
        cache_key="test_key",
        profile_count_verified=True,
        profile_count=2,
    )

    result = analyze(combined, spec, fetch_res)

    # 1. Check aggregate text in summary
    assert "1 of 2 profiles reached the feature" in result.summary

    # 2. Check shallower count in missing_data_notes
    assert any("profiles ended shallower than requested target depth" in note for note in result.missing_data_notes)
    assert any("SOFAR channel axis: 1 of 2 profiles reached the feature" in note for note in result.missing_data_notes)

