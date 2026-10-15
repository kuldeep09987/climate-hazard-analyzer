"""Ingest daily max temperature from Open-Meteo (ERA5 reanalysis) and cache in MongoDB."""
import datetime as dt
import time
import httpx
from cachetools import TTLCache
from .db import get_db

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
GRID = 0.25  # ERA5 native resolution; snapping also raises cache hit-rate

_geo_cache = TTLCache(maxsize=512, ttl=3600)


def snap(v: float) -> float:
    return round(round(v / GRID) * GRID, 2)


def cell_id(lat: float, lon: float) -> str:
    return f"{snap(lat):.2f}_{snap(lon):.2f}"


def _get_json(url: str, params: dict, tries: int = 3) -> dict:
    last = None
    for i in range(tries):
        try:
            r = httpx.get(url, params=params, timeout=45)
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError("upstream busy", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Upstream data service failed: {last}")


def geocode(q: str) -> list[dict]:
    key = q.strip().lower()
    if key in _geo_cache:
        return _geo_cache[key]
    data = _get_json(GEOCODE_URL, {"name": q, "count": 5, "language": "en", "format": "json"})
    out = [{"name": r["name"], "admin1": r.get("admin1"), "country": r.get("country"),
            "lat": r["latitude"], "lon": r["longitude"]} for r in data.get("results", [])]
    _geo_cache[key] = out
    return out


def ensure_years(lat: float, lon: float, y0: int, y1: int, need: str = "tmax") -> list[dict]:
    """Return per-year docs for [y0, y1] holding the `need` field ("tmax" or "precip").
    Fetches only the missing span; older docs lacking `need` are refetched."""
    db = get_db()
    cell = cell_id(lat, lon)
    have = {d["year"]: d for d in db.daily.find({"cell": cell, "year": {"$gte": y0, "$lte": y1}}, {"_id": 0})}
    missing = [y for y in range(y0, y1 + 1) if y not in have or need not in have[y]]
    if missing:
        data = _get_json(ARCHIVE_URL, {
            "latitude": snap(lat), "longitude": snap(lon),
            "start_date": f"{min(missing)}-01-01", "end_date": f"{max(missing)}-12-31",
            "daily": "temperature_2m_max,precipitation_sum",
            "temperature_unit": "celsius", "precipitation_unit": "mm", "timezone": "UTC",
        })
        d = data.get("daily", {})
        times, tmax, precip = d.get("time", []), d.get("temperature_2m_max", []), d.get("precipitation_sum", [])
        if not times or not (len(times) == len(tmax) == len(precip)):
            raise RuntimeError("Upstream returned an unexpected payload")
        by_year: dict[int, dict] = {}
        for t, a, p in zip(times, tmax, precip):
            row = by_year.setdefault(int(t[:4]), {"tmax": [], "precip": []})
            row["tmax"].append(a)    # None = gap
            row["precip"].append(p)
        now = dt.datetime.now(dt.timezone.utc)
        for y, arrs in by_year.items():
            if y in missing:
                doc = {"cell": cell, "year": y, "tmax": arrs["tmax"], "precip": arrs["precip"], "fetched_at": now}
                db.daily.update_one({"cell": cell, "year": y}, {"$set": doc}, upsert=True)
                have[y] = doc
    return [have[y] for y in sorted(have)]
