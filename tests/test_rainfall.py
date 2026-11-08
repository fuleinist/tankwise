"""Tests for rainfall loading."""

from __future__ import annotations

from datetime import date

import pytest

from tankwise.rainfall import RainfallError, demo_series, load_csv, window


def test_demo_series_is_deterministic():
    first = demo_series(days=400, seed=42)
    second = demo_series(days=400, seed=42)
    assert first.mm == second.mm
    assert first.dates[0] == date(1996, 1, 1)


def test_demo_series_length_matches_request():
    series = demo_series(days=730)
    assert len(series.dates) == 730
    assert len(series.mm) == 730


def test_series_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        from tankwise.rainfall import RainfallSeries

        RainfallSeries(dates=[date(2020, 1, 1)], mm=[1.0, 2.0], latitude=0, longitude=0, source="x")


def test_month_totals_have_twelve_entries():
    series = demo_series(days=800)
    months = series.month_totals()
    assert len(months) == 12
    assert [row["month"] for row in months] == list(range(1, 13))


def test_month_totals_sum_to_annual_mean():
    series = demo_series(days=365 * 3 + 1)
    months = series.month_totals()
    total = sum(row["mean_mm"] for row in months)
    assert total == pytest.approx(series.mean_annual_mm(), rel=0.02)


def test_load_csv_reads_fixture(tmp_path):
    path = tmp_path / "rain.csv"
    path.write_text(
        "date,mm\n2020-01-01,0.0\n2020-01-02,12.4\n2020-01-03,3.1\n", encoding="utf-8"
    )
    series = load_csv(path)
    assert series.mm == [0.0, 12.4, 3.1]
    assert series.dates[0] == date(2020, 1, 1)


def test_load_csv_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("date,mm\n", encoding="utf-8")
    with pytest.raises(RainfallError):
        load_csv(path)


def test_window_returns_full_years():
    start, end = window(30, today=date(2026, 11, 9))
    assert start == date(1996, 1, 1)
    assert end == date(2025, 12, 31)
    assert (end - start).days == 10957


def test_mean_annual_mm_is_close_to_total_over_years():
    series = demo_series(days=365 * 4)
    expected = series.total_mm / 4.0
    assert series.mean_annual_mm() == pytest.approx(expected, rel=0.02)