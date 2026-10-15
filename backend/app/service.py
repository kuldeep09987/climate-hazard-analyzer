import datetime as dt
import threading
from .db import get_db
from .ingest import ensure_years, cell_id, snap
from . import hazards, trends

_lock = threading.Lock()  # avoid duplicate upstream fetches under concurrent requests
VERSION = "v2"


def compute(hazard: str, docs: list[dict], lat: float, lon: float, y0: int, y1: int) -> dict:
    r = hazards.RUNNERS[hazard](docs, y0, y1)
    meta = hazards.META[hazard]
    trend, insight = trends.summarize(r["annual"], meta)
    quality = r["quality"]
    quality["years_excluded"] = [a["year"] for a in r["annual"] if not a["valid"]]
    return {
        "hazard": hazard, "version": VERSION, "cached": False,
        "meta": {k: v for k, v in meta.items() if k != "caveats"},
        "region": {"lat": snap(lat), "lon": snap(lon), "requested_lat": lat, "requested_lon": lon},
        "period": {"start": y0, "end": y1},
        "definition": hazards.definition(hazard, y0, y1),
        "threshold": r["threshold"],
        "annual": r["annual"],
        "top_events": sorted(r["events"], key=lambda e: (-e["duration"], -abs(e["peak"])))[:10],
        "trend": trend, "insight": insight, "quality": quality,
        "source": "Open-Meteo Historical Weather API (ERA5 reanalysis), daily temperature_2m_max / precipitation_sum",
    }


def get_analysis(hazard: str, lat: float, lon: float, y0: int, y1: int) -> dict:
    db = get_db()
    key = f"{hazard}:{cell_id(lat, lon)}:{y0}:{y1}:{VERSION}"
    doc = db.analyses.find_one({"key": key}, {"_id": 0, "created_at": 0})
    if doc:
        doc["cached"] = True
        return doc
    with _lock:
        docs = ensure_years(lat, lon, y0, y1, need="tmax" if hazard == "heatwave" else "precip")
        result = compute(hazard, docs, lat, lon, y0, y1)
    result["key"] = key
    db.analyses.update_one({"key": key},
                           {"$set": {**result, "created_at": dt.datetime.now(dt.timezone.utc)}}, upsert=True)
    result.pop("_id", None)
    return result
