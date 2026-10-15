import csv
import datetime as dt
import io
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import ingest, service

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app = FastAPI(title="Climate Hazard Trend Analyzer", docs_url="/docs")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"], allow_headers=["*"],
)

Hazard = Literal["heatwave", "heavy_rainfall", "drought"]
LAST_FULL_YEAR = dt.date.today().year - 1


def validated(start_year: int, end_year: int):
    if end_year > LAST_FULL_YEAR:
        raise HTTPException(422, f"end_year must be <= {LAST_FULL_YEAR} (last complete year)")
    if end_year - start_year < 14:
        raise HTTPException(422, "Need a range of at least 15 years for a stable 95th percentile")
    if end_year - start_year > 80:
        raise HTTPException(422, "Range too long (max 80 years)")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/geocode")
@limiter.limit("30/minute")
def geocode(request: Request, q: str = Query(..., min_length=2, max_length=80)):
    try:
        return ingest.geocode(q)
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.get("/api/analysis")
@limiter.limit("20/minute")
def analysis(request: Request,
             lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
             start_year: int = Query(1990, ge=1950), end_year: int = Query(2020, ge=1950),
             hazard: Hazard = "heatwave"):
    validated(start_year, end_year)
    try:
        return service.get_analysis(hazard, lat, lon, start_year, end_year)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(503, f"Backend error: {type(e).__name__}: {e}")


@app.get("/api/export.csv")
@limiter.limit("10/minute")
def export_csv(request: Request,
               lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
               start_year: int = Query(1990, ge=1950), end_year: int = Query(2020, ge=1950),
               hazard: Hazard = "heatwave"):
    validated(start_year, end_year)
    try:
        data = service.get_analysis(hazard, lat, lon, start_year, end_year)
    except Exception:
        raise HTTPException(502, "Could not build export")
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["year", "events", "days", "max_duration", "mean_intensity", "days_roll5", "days_fit", "coverage", "valid"]
    w.writerow(cols)
    for a in data["annual"]:
        w.writerow([a.get(c) for c in cols])
    name = f'{hazard}_{data["region"]["lat"]}_{data["region"]["lon"]}.csv'
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
