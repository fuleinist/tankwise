"""Daily rainfall providers.

Primary provider: Open-Meteo Archive API (ERA5). Free, no API key.
Cache: SQLite, so repeat plans do not refetch 30 years of data.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE_PATH = Path.home() / ".tankwise" / "cache.sqlite3"


class RainfallError(RuntimeError):
    """Raised when no rainfall series can be loaded."""


@dataclass
class RainfallSeries:
    dates: list[date]
    mm: list[float]
    latitude: float
    longitude: float
    source: str
    elevation_m: float | None = None
    timezone: str | None = None

    def __post_init__(self) -> None:
        if len(self.dates) != len(self.mm):
            raise ValueError("dates and mm must have the same length")
        if not self.dates:
            raise ValueError("rainfall series is empty")

    @property
    def total_mm(self) -> float:
        return float(sum(self.mm))

    @property
    def years(self) -> float:
        return len(self.dates) / 365.25

    def mean_annual_mm(self) -> float:
        return self.total_mm / self.years if self.years else 0.0

    def month_totals(self) -> list[dict]:
        """Mean monthly rainfall in mm across the whole record."""
        sums = [0.0] * 12
        years = set()
        for day, value in zip(self.dates, self.mm):
            sums[day.month - 1] += value
            years.add(day.year)
        year_count = max(1, len(years))
        return [
            {"month": m + 1, "mean_mm": round(sums[m] / year_count, 1)}
            for m in range(12)
        ]


def _cache_key(lat: float, lon: float, start: date, end: date) -> str:
    return f"{lat:.2f},{lon:.2f},{start.isoformat()},{end.isoformat()}"


def _read_cache(key: str) -> RainfallSeries | None:
    try:
        if not CACHE_PATH.exists():
            return None
        with sqlite3.connect(CACHE_PATH) as conn:
            row = conn.execute(
                "SELECT payload FROM rainfall_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return RainfallSeries(
            dates=[date.fromisoformat(d) for d in data["dates"]],
            mm=[float(v) for v in data["mm"]],
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            source=str(data["source"]),
            elevation_m=data.get("elevation_m"),
            timezone=data.get("timezone"),
        )
    except (sqlite3.Error, ValueError, KeyError):
        return None


def _write_cache(key: str, series: RainfallSeries) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "dates": [d.isoformat() for d in series.dates],
            "mm": series.mm,
            "latitude": series.latitude,
            "longitude": series.longitude,
            "source": series.source,
            "elevation_m": series.elevation_m,
            "timezone": series.timezone,
        }
        with sqlite3.connect(CACHE_PATH) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS rainfall_cache "
                "(cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO rainfall_cache (cache_key, payload) VALUES (?, ?)",
                (key, json.dumps(payload)),
            )
    except sqlite3.Error:
        # A cache failure must never block a plan.
        pass


def fetch_open_meteo(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    timeout: float = 30.0,
    use_cache: bool = True,
) -> RainfallSeries:
    """Fetch daily precipitation from Open-Meteo Archive."""
    if end <= start:
        raise ValueError("end date must be after start date")

    key = _cache_key(latitude, longitude, start, end)
    if use_cache:
        cached = _read_cache(key)
        if cached is not None:
            return cached

    params = {
        "latitude": f"{latitude:.5f}",
        "longitude": f"{longitude:.5f}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "precipitation_sum",
        "timezone": "auto",
    }
    url = f"{ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tankwise/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RainfallError(f"Open-Meteo request failed: {exc}") from exc

    daily = payload.get("daily") or {}
    raw_dates = daily.get("time") or []
    raw_mm = daily.get("precipitation_sum") or []
    if not raw_dates or not raw_mm:
        raise RainfallError("Open-Meteo returned no precipitation data")

    dates: list[date] = []
    mm: list[float] = []
    for stamp, value in zip(raw_dates, raw_mm):
        if value is None:
            # A missing day is treated as no rain. The record keeps its length.
            value = 0.0
        dates.append(date.fromisoformat(stamp))
        mm.append(max(0.0, float(value)))

    series = RainfallSeries(
        dates=dates,
        mm=mm,
        latitude=float(payload.get("latitude", latitude)),
        longitude=float(payload.get("longitude", longitude)),
        source="Open-Meteo Archive (ERA5)",
        elevation_m=payload.get("elevation"),
        timezone=payload.get("timezone"),
    )
    if use_cache:
        _write_cache(key, series)
    return series


def load_csv(path: str | Path) -> RainfallSeries:
    """Load a bundled fixture with `date,mm` rows."""
    file_path = Path(path)
    dates: list[date] = []
    mm: list[float] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("date"):
                continue
            stamp, _, value = line.partition(",")
            dates.append(date.fromisoformat(stamp.strip()))
            mm.append(max(0.0, float(value)))
    if not dates:
        raise RainfallError(f"no rows in {file_path}")
    return RainfallSeries(
        dates=dates,
        mm=mm,
        latitude=0.0,
        longitude=0.0,
        source=f"fixture:{file_path.name}",
        timezone=None,
    )


def window(years: int = 30, today: date | None = None) -> tuple[date, date]:
    """Return the last `years` full calendar years."""
    end_year = (today or date.today()).year - 1
    return date(end_year - years + 1, 1, 1), date(end_year, 12, 31)


def demo_series(days: int = 365 * 30, seed: int = 7) -> RainfallSeries:
    """Deterministic synthetic rainfall for tests and offline demos.

    The pattern is a wet/dry seasonal cycle with random wet days. It is not a
    climate record. Use it only when no network is available.
    """
    import random

    rng = random.Random(seed)
    start = date(1996, 1, 1)
    dates: list[date] = []
    mm: list[float] = []
    for index in range(days):
        day = start + timedelta(days=index)
        phase = (day.month - 1) / 12.0 * 6.28318
        wet_chance = 0.30 + 0.10 * (0.5 + 0.5 * __import__("math").cos(phase))
        value = 0.0
        if rng.random() < wet_chance:
            value = round(rng.expovariate(1 / 9.0), 2)
        dates.append(day)
        mm.append(value)
    return RainfallSeries(
        dates=dates,
        mm=mm,
        latitude=-33.77,
        longitude=151.18,
        source="synthetic-demo",
        timezone="Australia/Sydney",
    )