# Climate Hazard Trend Analyzer (Heatwaves)

React + FastAPI + MongoDB. Pick a place (search, map click, or lat/lon box), a hazard (Heatwave by default, plus Heavy rainfall
and Drought) and a year range; get frequency / duration / intensity time series, trend statistics and a plain-language insight.

## Run locally
```bash
docker compose up -d mongo
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload            # http://localhost:8000/docs

cd ../frontend && npm install && npm run dev   # http://localhost:5173
```
Env: `MONGO_URI`, `MONGO_DB`, `ALLOWED_ORIGINS` (backend); `VITE_API_URL` (frontend).

## Architecture
Browser -> `/api/analysis` -> check `analyses` collection -> (miss) fetch missing years from Open-Meteo,
store in `daily` collection (one doc per 0.25 deg cell-year) -> clean -> detect -> trends -> store -> JSON.
Repeat requests are served from MongoDB; raw years are reused across overlapping ranges.

## Data source
Open-Meteo Historical Weather API (ERA5 reanalysis, `temperature_2m_max` deg C and `precipitation_sum` mm, ~25 km grid). No API key.

## Hazard logic
- **Heatwave (default):** per-calendar-day 95th percentile of Tmax (+/-7-day window, over the selected period); event = 3+ consecutive days strictly above it. Intensity = mean excess over threshold (deg C).
- **Heavy rainfall:** day with rainfall above the 95th percentile of wet days (>= 1 mm); consecutive heavy days form one event. Intensity = mean rain on those days (mm). Rain is never interpolated.
- **Drought:** SPI-3 (3-month rainfall totals, gamma fit per calendar month, zero-rain correction); drought month = SPI-3 <= -1; event = 2+ consecutive months. Intensity = mean -SPI.
- **Per year (all hazards):** events, hazard days/months, longest event, mean intensity.
- **Trends:** OLS regression, Mann-Kendall test with Sen's slope, 5-year rolling mean. The insight compares the first vs last 10 valid years and reports significance.

## Data handling
Gaps (nulls) kept as gaps; temperature gaps <= 2 days are interpolated (rain never is); values outside -90..60 C or >25 C from
the 15-day rolling median removed; years with <90% coverage excluded from trends and greyed out in the chart.

## Security / performance
Validated query params (ranges, Literal hazard), no user-controlled upstream URLs, upstream timeouts + retries,
per-IP rate limits (slowapi), CORS allow-list, geocode TTL cache, Mongo TTL on analyses, read-only GET API.

## Assumptions
- A lat/lon box is reduced to its centre point (data is gridded point data).
- Threshold baseline = selected period; end year must be a complete year; minimum 15 years.
- Drought here is meteorological (rainfall deficit only). Heatwave thresholds in narrow-range tropical climates flag small excesses; see caveats in the UI.
- Percentage change from a zero baseline is described in absolute terms.

## With more time
Area-averaged boxes, fixed WMO 1991-2020 baseline option, heat index (humidity), PDF export, tests,
background ingestion jobs, Redis-backed rate limiting.

## AI tools used
**Claude (Anthropic)** was the main tool.
- Generated the first version of the backend (FastAPI, Open-Meteo ingestion, MongoDB caching, heatwave detection, Mann-Kendall / regression trends) and the React frontend (Chart.js, Leaflet).
- Added the heavy rainfall (95th percentile of wet days) and drought (SPI-3) hazards.
- Helped debug setup problems: a numpy build failure on Python 3.14, an old backend still holding port 8000, and a MongoDB connection refused error.
- Drafted this README structure and interview practice questions.

**What I did myself**
- Chose the heatwave definition and checked it against the brief: 3+ days above the per-calendar-day 95th percentile.
- Ran the app locally with Docker MongoDB, tested several locations, and read the outputs critically. For example, I noticed Mangaluru's detected heatwaves exceed the threshold by only 0.2 to 1.2 °C, and documented that as a limitation.
- Reviewed and can explain every module, and changed code live to test it.
- [Add anything else that is true: deployment, bug fixes, tests, UI tweaks, other AI tools such as ChatGPT or Gemini.]

**Verification:** I tested the detection and trend logic with synthetic data and compared results across locations. The sources and limitations are listed above.
