"""Hazard detection: heatwave, heavy rainfall, drought.

Heatwave:  >= 3 consecutive days with Tmax above the 95th percentile of the same calendar day (+/-7-day window).
Heavy rain: day with rainfall above the 95th percentile of wet days (>= 1 mm) in the period; consecutive days = 1 event.
Drought:   month with SPI-3 <= -1 (gamma-fit per calendar month); event = 2+ consecutive such months.

Every runner returns {quality, threshold, events, annual} with the same shapes, so the API/UI are hazard-agnostic.
"""
import numpy as np
import pandas as pd
from scipy import stats

WINDOW, PCT, MIN_RUN = 7, 95, 3
MIN_COVERAGE = 0.9           # years with less valid data are excluded from trends
PLAUSIBLE = (-90.0, 60.0)    # deg C
SPIKE_C = 25.0               # departure from 15-day rolling median flagged as spike
WET_MM, MAX_PRECIP_MM = 1.0, 1500.0
SPI_THRESHOLD, SPI_MIN_MONTHS, DROUGHT_MIN_COVERAGE = -1.0, 2, 0.8

META = {
    "heatwave": {"label": "Heatwave", "days_label": "Heatwave days", "per_year_unit": "days/year",
                 "duration_unit": "days", "peak_label": "Peak Tmax (°C)",
                 "intensity_label": "Mean excess over threshold (°C)",
                 "caveats": [
                     "Thresholds are percentiles of the selected period itself, so ~5% of days exceed them by construction; the trend shows how those days shift and cluster over time.",
                     "Data is ERA5 reanalysis on a ~25 km grid, not a station record; local and urban effects are smoothed out.",
                     "Annual counts are small integers and noisy; a percentage change off a low base is fragile."]},
    "heavy_rainfall": {"label": "Heavy rainfall", "days_label": "Heavy-rain days", "per_year_unit": "days/year",
                       "duration_unit": "days", "peak_label": "Peak daily rain (mm)",
                       "intensity_label": "Mean rain on heavy days (mm)",
                       "caveats": [
                           "The threshold is the 95th percentile of wet-day (>= 1 mm) rainfall over the selected period, so it is relative to this period.",
                           "ERA5 rainfall is modelled on a ~25 km grid and tends to underestimate intense local storms.",
                           "Extreme rainfall is highly variable; 30-year trends are rarely statistically significant."]},
    "drought": {"label": "Drought", "days_label": "Drought months", "per_year_unit": "months/year",
                "duration_unit": "months", "peak_label": "Lowest SPI-3",
                "intensity_label": "Mean severity (-SPI-3)",
                "caveats": [
                    "Meteorological drought only (rainfall deficit via SPI-3); evaporation, soil moisture and irrigation are ignored.",
                    "SPI is fitted over the selected period only, so short ranges give uncertain gamma fits.",
                    "In strongly seasonal climates, dry-season months are always dry and rarely flagged; the signal comes from wet-season deficits."]},
}


def definition(hazard: str, y0: int, y1: int) -> str:
    return {
        "heatwave": f"{MIN_RUN}+ consecutive days with Tmax above the {PCT}th percentile of the same calendar day (+/-{WINDOW}-day window), {y0}-{y1} baseline.",
        "heavy_rainfall": f"Day with rainfall above the {PCT}th percentile of wet days (>= {WET_MM} mm), {y0}-{y1}; consecutive heavy days form one event.",
        "drought": f"Month with SPI-3 <= {SPI_THRESHOLD} (gamma-fit per calendar month, {y0}-{y1}); an event is {SPI_MIN_MONTHS}+ consecutive such months.",
    }[hazard]


# ---------------- shared helpers ----------------
def to_series(docs: list[dict], key: str = "tmax") -> pd.Series:
    parts = []
    for d in sorted(docs, key=lambda d: d["year"]):
        arr = d[key]
        idx = pd.date_range(f"{d['year']}-01-01", periods=len(arr), freq="D")
        parts.append(pd.Series([np.nan if v is None else float(v) for v in arr], index=idx))
    return pd.concat(parts)


def _runs(above: np.ndarray):
    d = np.diff(np.concatenate([[0], above.astype(int), [0]]))
    return np.where(d == 1)[0], np.where(d == -1)[0]  # ends exclusive


def _annual(events: list[dict], cov: dict, y0: int, y1: int, min_cov: float) -> list[dict]:
    rows = []
    for y in range(y0, y1 + 1):
        c = float(cov.get(y, 0.0))
        ev = [e for e in events if e["year"] == y]
        rows.append({
            "year": y, "coverage": round(c, 3), "valid": c >= min_cov,
            "events": len(ev), "days": sum(e["duration"] for e in ev),
            "max_duration": max((e["duration"] for e in ev), default=0),
            "mean_intensity": round(float(np.average([e["intensity"] for e in ev],
                                                     weights=[e["duration"] for e in ev])), 2) if ev else None,
        })
    return rows


def _coverage(s: pd.Series) -> dict:
    return s.notna().groupby(s.index.year).mean().to_dict()


# ---------------- heatwave ----------------
def clean_temp(s: pd.Series) -> tuple[pd.Series, dict]:
    missing_raw = int(s.isna().sum())
    implausible = (s < PLAUSIBLE[0]) | (s > PLAUSIBLE[1])
    s = s.mask(implausible)
    med = s.rolling(15, center=True, min_periods=5).median()
    spikes = (s - med).abs() > SPIKE_C
    s = s.mask(spikes)
    before = int(s.isna().sum())
    s = s.interpolate(limit=2, limit_area="inside")  # fill gaps of <= 2 days only
    filled = before - int(s.isna().sum())
    return s, {"days": int(len(s)), "missing_raw": missing_raw,
               "implausible_removed": int(implausible.sum()), "spikes_removed": int(spikes.sum()),
               "gaps_interpolated": filled, "still_missing": int(s.isna().sum())}


def _cols(idx: pd.DatetimeIndex) -> np.ndarray:
    doy = idx.dayofyear.values
    return np.where(idx.is_leap_year & (doy >= 60), doy - 1, doy) - 1  # Feb 29 -> Feb 28 column


def daily_thresholds(s: pd.Series) -> np.ndarray:
    cols, years = _cols(s.index), s.index.year.values
    y0 = years.min()
    keep = ~(s.index.is_leap_year & (s.index.dayofyear.values == 60))
    mat = np.full((years.max() - y0 + 1, 365), np.nan)
    mat[years[keep] - y0, cols[keep]] = s.values[keep]
    thr = np.full(365, np.nan)
    for d in range(365):
        vals = mat[:, [(d + k) % 365 for k in range(-WINDOW, WINDOW + 1)]]
        vals = vals[~np.isnan(vals)]
        if vals.size >= 30:
            thr[d] = np.percentile(vals, PCT)
    return thr


def run_heatwave(docs, y0, y1) -> dict:
    s, quality = clean_temp(to_series(docs, "tmax"))
    thr = daily_thresholds(s)
    t = thr[_cols(s.index)]
    above = np.nan_to_num(s.values, nan=-999) > np.nan_to_num(t, nan=999)
    events = []
    for a, b in zip(*_runs(above)):
        if b - a >= MIN_RUN:
            events.append({"year": int(s.index[a].year), "start": s.index[a].date().isoformat(),
                           "end": s.index[b - 1].date().isoformat(), "duration": int(b - a),
                           "peak": round(float(s.values[a:b].max()), 1),
                           "intensity": round(float((s.values[a:b] - t[a:b]).mean()), 2)})
    threshold = {"min": round(float(np.nanmin(thr)), 1), "max": round(float(np.nanmax(thr)), 1),
                 "mean": round(float(np.nanmean(thr)), 1), "unit": "°C"}
    return {"quality": quality, "threshold": threshold, "events": events,
            "annual": _annual(events, _coverage(s), y0, y1, MIN_COVERAGE)}


# ---------------- heavy rainfall ----------------
def run_rainfall(docs, y0, y1) -> dict:
    raw = to_series(docs, "precip")
    bad = (raw < 0) | (raw > MAX_PRECIP_MM)
    s = raw.mask(bad)  # rain is never interpolated: a gap stays a gap
    quality = {"days": int(len(s)), "missing_raw": int(raw.isna().sum()), "implausible_removed": int(bad.sum()),
               "spikes_removed": 0, "gaps_interpolated": 0, "still_missing": int(s.isna().sum())}
    wet = s[s >= WET_MM].dropna()
    if len(wet) < 100:
        raise ValueError("Too few wet days at this location to define a rainfall threshold")
    thr = float(np.percentile(wet.values, PCT))
    above = np.nan_to_num(s.values, nan=-1) > thr
    events = []
    for a, b in zip(*_runs(above)):
        seg = s.values[a:b]
        events.append({"year": int(s.index[a].year), "start": s.index[a].date().isoformat(),
                       "end": s.index[b - 1].date().isoformat(), "duration": int(b - a),
                       "peak": round(float(seg.max()), 1), "intensity": round(float(seg.mean()), 1)})
    thr_r = round(thr, 1)
    return {"quality": quality, "threshold": {"min": thr_r, "max": thr_r, "mean": thr_r, "unit": "mm/day"},
            "events": events, "annual": _annual(events, _coverage(s), y0, y1, MIN_COVERAGE)}


# ---------------- drought (SPI-3) ----------------
def spi3(s: pd.Series) -> pd.Series:
    g = s.resample("MS")
    tot, cnt = g.sum(min_count=1), g.count()
    tot = tot.where(cnt >= 0.9 * tot.index.days_in_month)   # month needs >= 90% valid days
    roll = tot.rolling(3).sum()                              # NaN if any month in window is NaN
    spi = pd.Series(np.nan, index=roll.index)
    for m in range(1, 13):
        x = roll[roll.index.month == m].dropna()
        nz = x[x > 0]
        if len(x) < 20 or len(nz) < 10:
            continue
        q = 1 - len(nz) / len(x)                             # probability of a zero total
        a, _, scale = stats.gamma.fit(nz.values, floc=0)
        h = np.clip(q + (1 - q) * stats.gamma.cdf(x.values, a, loc=0, scale=scale), 0.001, 0.999)
        spi.loc[x.index] = stats.norm.ppf(h)
    return spi


def run_drought(docs, y0, y1) -> dict:
    raw = to_series(docs, "precip")
    bad = (raw < 0) | (raw > MAX_PRECIP_MM)
    s = raw.mask(bad)
    quality = {"days": int(len(s)), "missing_raw": int(raw.isna().sum()), "implausible_removed": int(bad.sum()),
               "spikes_removed": 0, "gaps_interpolated": 0, "still_missing": int(s.isna().sum())}
    spi = spi3(s)
    if spi.notna().sum() < 36:
        raise ValueError("Not enough rainfall data to compute SPI-3")
    vals = spi.values
    dry = np.nan_to_num(vals, nan=0.0) <= SPI_THRESHOLD
    events = []
    for a, b in zip(*_runs(dry)):
        if b - a >= SPI_MIN_MONTHS:
            seg = vals[a:b]
            events.append({"year": int(spi.index[a].year), "start": spi.index[a].date().isoformat(),
                           "end": (spi.index[b - 1] + pd.offsets.MonthEnd(0)).date().isoformat(),
                           "duration": int(b - a), "peak": round(float(seg.min()), 2),
                           "intensity": round(float((-seg).mean()), 2)})
    cov = spi.notna().groupby(spi.index.year).mean().to_dict()
    return {"quality": quality, "threshold": {"min": SPI_THRESHOLD, "max": SPI_THRESHOLD, "mean": SPI_THRESHOLD, "unit": "SPI-3"},
            "events": events, "annual": _annual(events, cov, y0, y1, DROUGHT_MIN_COVERAGE)}


RUNNERS = {"heatwave": run_heatwave, "heavy_rainfall": run_rainfall, "drought": run_drought}
