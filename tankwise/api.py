"""FastAPI application for tankwise."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Assumptions, ROOF_AREA_DEFAULT_M2
from .demand import build_demand
from .geo import GeoError, geocode, roof_area
from .rainfall import RainfallError, demo_series, fetch_open_meteo, window
from .simulate import simulate
from .sizing import default_sizes, economics, recommend, sweep_sizes

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="tankwise",
    version=__version__,
    description="Rainwater tank planner. Size a tank from 30 years of local rainfall.",
)


class PlanRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    roof_area_m2: float | None = Field(None, ge=5, le=5000)
    occupants: int = Field(4, ge=0, le=30)
    garden_area_m2: float = Field(100.0, ge=0, le=10000)
    tank_litres: float = Field(5000, ge=500, le=50000)
    target_coverage: float = Field(0.90, ge=0.05, le=0.99)
    water_price_per_kl: float = Field(2.35, ge=0, le=20)
    rebate_aud: float = Field(0.0, ge=0, le=20000)
    include_garden: bool = True
    include_toilet: bool = True
    include_laundry: bool = True
    runoff_coefficient: float = Field(0.85, ge=0.1, le=1.0)
    first_flush_mm: float = Field(1.0, ge=0, le=10)
    years: int = Field(30, ge=5, le=70)
    offline_demo: bool = False


class RoofRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "engine": "stdlib"}


@app.get("/api/geocode")
def api_geocode(q: str = Query(..., min_length=2, max_length=120)) -> dict:
    try:
        results = geocode(q)
    except GeoError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"query": q, "results": results}


@app.post("/api/roof")
def api_roof(payload: RoofRequest) -> dict:
    try:
        return roof_area(payload.latitude, payload.longitude)
    except GeoError as exc:
        return {
            "roof_area_m2": ROOF_AREA_DEFAULT_M2,
            "confidence": "fallback",
            "source": "default assumption",
            "note": f"Roof lookup failed. Default used. {exc}",
        }


@app.post("/api/plan")
def api_plan(payload: PlanRequest) -> dict:
    assumptions = Assumptions(
        occupants=payload.occupants,
        garden_area_m2=payload.garden_area_m2,
        include_garden=payload.include_garden,
        include_toilet=payload.include_toilet,
        include_laundry=payload.include_laundry,
        runoff_coefficient=payload.runoff_coefficient,
        first_flush_mm=payload.first_flush_mm,
        water_price_per_kl=payload.water_price_per_kl,
        rebate_aud=payload.rebate_aud,
        target_coverage=payload.target_coverage,
    )

    latitude, longitude = payload.latitude, payload.longitude
    roof = payload.roof_area_m2
    roof_meta = {"source": "user input", "confidence": "high"}
    if roof is None:
        try:
            lookup = roof_area(latitude, longitude)
            roof = float(lookup["roof_area_m2"])
            roof_meta = {
                "source": lookup["source"],
                "confidence": lookup["confidence"],
            }
        except GeoError as exc:
            roof = ROOF_AREA_DEFAULT_M2
            roof_meta = {
                "source": "default assumption",
                "confidence": "low",
                "note": str(exc),
            }

    start, end = window(payload.years)
    try:
        if payload.offline_demo:
            series = demo_series(days=payload.years * 365 + 8)
        else:
            series = fetch_open_meteo(latitude, longitude, start, end)
    except RainfallError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    southern = latitude < 0
    demand = build_demand(series.dates, assumptions, southern_hemisphere=southern)

    result = simulate(
        rainfall=series,
        demand=demand,
        capacity_l=payload.tank_litres,
        catchment_m2=roof,
        runoff_coefficient=assumptions.runoff_coefficient,
        first_flush_mm=assumptions.first_flush_mm,
    )

    options = sweep_sizes(
        rainfall=series,
        demand=demand,
        catchment_m2=roof,
        assumptions=assumptions,
        sizes=default_sizes(),
    )

    return {
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": series.timezone,
            "elevation_m": series.elevation_m,
            "rainfall_source": series.source,
            "start_date": series.dates[0].isoformat(),
            "end_date": series.dates[-1].isoformat(),
        },
        "roof": {
            "area_m2": round(roof, 1),
            **roof_meta,
        },
        "rainfall_summary": {
            "mean_annual_mm": round(series.mean_annual_mm(), 1),
            "years": round(series.years, 1),
            "months": series.month_totals(),
        },
        "demand_summary": demand.summary(),
        "tank": {
            "capacity_litres": payload.tank_litres,
            "catchment_m2": round(roof, 1),
            "runoff_coefficient": assumptions.runoff_coefficient,
            "first_flush_mm": assumptions.first_flush_mm,
        },
        "result": result.metrics,
        "economics": economics(result.metrics, payload.tank_litres, assumptions),
        "sweep": [option.to_dict() for option in options],
        "recommendation": recommend(options, assumptions.target_coverage),
        "monthly": result.monthly_series(months=36),
        "assumptions": {
            **assumptions.to_dict(),
            "initial_fill_fraction": 0.25,
            "spinup_days": 90,
            "source_note": (
                "Rainfall from Open-Meteo Archive (ERA5). Roof area from "
                "OpenStreetMap. Costs are estimates, not quotes."
            ),
        },
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")