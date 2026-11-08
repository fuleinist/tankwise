"""Location helpers: geocoding and roof area estimation.

Both providers are free and need no API key.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class GeoError(RuntimeError):
    """Raised when a location service fails."""


def geocode(query: str, count: int = 5, timeout: float = 20.0) -> list[dict]:
    """Search a place name or postcode."""
    query = (query or "").strip()
    if not query:
        return []

    params = {
        "name": query,
        "count": str(count),
        "language": "en",
        "format": "json",
    }
    url = f"{GEOCODE_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tankwise/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeoError(f"geocoding failed: {exc}") from exc

    results: list[dict] = []
    for item in payload.get("results") or []:
        results.append(
            {
                "name": item.get("name"),
                "admin1": item.get("admin1"),
                "country": item.get("country"),
                "postcode": item.get("postcode"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "timezone": item.get("timezone"),
                "label": _label(item),
            }
        )
    return results


def _label(item: dict[str, Any]) -> str:
    parts = [item.get("name"), item.get("admin1"), item.get("country")]
    return ", ".join(part for part in parts if part)


def _polygon_area_m2(points: list[tuple[float, float]]) -> float:
    """Area of a lat/lon polygon on a local flat projection."""
    if len(points) < 3:
        return 0.0
    lat0 = sum(p[0] for p in points) / len(points)
    lon0 = sum(p[1] for p in points) / len(points)
    metres_per_deg_lat = 110_540.0
    metres_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))

    projected = [
        ((lon - lon0) * metres_per_deg_lon, (lat - lat0) * metres_per_deg_lat)
        for lat, lon in points
    ]
    total = 0.0
    for index in range(len(projected)):
        x1, y1 = projected[index - 1]
        x2, y2 = projected[index]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def roof_area(latitude: float, longitude: float, radius_m: float = 60.0,
              timeout: float = 15.0) -> dict:
    """Estimate the main building's roof area from OpenStreetMap footprints.

    The result is the largest building footprint near the point, scaled by 1.15
    to allow for roof pitch. Callers must treat the value as an estimate.
    """
    query = f"""
    [out:json][timeout:10];
    way(around:{radius_m:.0f},{latitude:.6f},{longitude:.6f})["building"];
    out geom;
    """
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={
            "User-Agent": "tankwise/0.1 (rainwater tank planner)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeoError(f"Overpass request failed: {exc}") from exc

    best = 0.0
    count = 0
    for element in payload.get("elements") or []:
        geometry = element.get("geometry") or []
        points = [(node["lat"], node["lon"]) for node in geometry if "lat" in node]
        if len(points) < 3:
            continue
        area = _polygon_area_m2(points)
        count += 1
        best = max(best, area)

    if best <= 0:
        raise GeoError("no building footprint found near this point")

    pitched = best * 1.15
    confidence = "high" if best >= 80 else "medium" if best >= 40 else "low"
    return {
        "roof_area_m2": round(pitched, 1),
        "footprint_m2": round(best, 1),
        "buildings_found": count,
        "confidence": confidence,
        "source": "OpenStreetMap Overpass",
    }