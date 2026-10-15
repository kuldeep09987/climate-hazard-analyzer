import { useState } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import icon from "leaflet/dist/images/marker-icon.png";
import iconShadow from "leaflet/dist/images/marker-shadow.png";
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Legend,
} from "chart.js";
import { Chart } from "react-chartjs-2";
import { API, get } from "./api";

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Legend);
L.Marker.prototype.options.icon = L.icon({ iconUrl: icon, shadowUrl: iconShadow, iconAnchor: [12, 41] });

const LAST_YEAR = new Date().getFullYear() - 1;

function ClickPicker({ onPick }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

export default function App() {
  const [pos, setPos] = useState({ lat: 12.87, lon: 74.84, label: "Mangaluru" });
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [box, setBox] = useState({ s: "", w: "", n: "", e: "" });
  const [hazard, setHazard] = useState("heatwave");
  const [start, setStart] = useState(1990);
  const [end, setEnd] = useState(Math.min(2020, LAST_YEAR));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search(e) {
    e.preventDefault();
    setError("");
    try { setResults(await get("/api/geocode", { q })); } catch (err) { setError(err.message); }
  }

  function useBox() {
    const [s, w, n, e] = [box.s, box.w, box.n, box.e].map(Number);
    const empty = [box.s, box.w, box.n, box.e].some((v) => v === "");
    if (empty || [s, w, n, e].some(Number.isNaN) || s >= n || w >= e)
      return setError("Enter a valid box: south < north, west < east.");
    setPos({ lat: (s + n) / 2, lon: (w + e) / 2, label: "Box centre" });
    setError("");
  }

  async function analyze() {
    setLoading(true); setError(""); setData(null);
    try {
      setData(await get("/api/analysis", { lat: pos.lat, lon: pos.lon, start_year: start, end_year: end, hazard }));
    } catch (err) { setError(err.message); }
    setLoading(false);
  }

  const a = data?.annual || [];
  const m = data?.meta || {};
  const labels = a.map((r) => r.year);
  const daysChart = {
    labels,
    datasets: [
      { type: "bar", label: m.days_label, data: a.map((r) => r.days),
        backgroundColor: a.map((r) => (r.valid ? "#e4572e" : "#bbb")) },
      { type: "line", label: "5-yr rolling mean", data: a.map((r) => r.days_roll5), borderColor: "#17bebb", pointRadius: 0, tension: 0.3 },
      { type: "line", label: "Linear trend", data: a.map((r) => r.days_fit), borderColor: "#222", borderDash: [6, 4], pointRadius: 0 },
    ],
  };
  const eventChart = {
    labels,
    datasets: [
      { type: "bar", label: "Events", data: a.map((r) => r.events), backgroundColor: "#f3a712", yAxisID: "y" },
      { type: "line", label: `Longest event (${m.duration_unit})`, data: a.map((r) => r.max_duration), borderColor: "#6a4c93", yAxisID: "y1", pointRadius: 2 },
    ],
  };
  const intensityChart = {
    labels,
    datasets: [{ type: "line", label: m.intensity_label, data: a.map((r) => r.mean_intensity),
      borderColor: "#c1121f", spanGaps: true, pointRadius: 3 }],
  };
  const csvUrl = `${API}/api/export.csv?` + new URLSearchParams({ lat: pos.lat, lon: pos.lon, start_year: start, end_year: end, hazard });

  return (
    <div className="page">
      <h1>Climate Hazard Trend Analyzer</h1>

      <section className="panel controls">
        <div>
          <form onSubmit={search} className="row">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search city or state" minLength={2} maxLength={80} required />
            <button>Search</button>
          </form>
          {results.map((r, i) => (
            <button key={i} className="link" onClick={() => { setPos({ lat: r.lat, lon: r.lon, label: r.name }); setResults([]); }}>
              {r.name}{r.admin1 ? `, ${r.admin1}` : ""}, {r.country}
            </button>
          ))}
          <div className="row small">
            <span>Box:</span>
            {["s", "w", "n", "e"].map((k) => (
              <input key={k} type="number" step="any" placeholder={{ s: "S lat", w: "W lon", n: "N lat", e: "E lon" }[k]}
                value={box[k]} onChange={(ev) => setBox({ ...box, [k]: ev.target.value })} />
            ))}
            <button onClick={useBox}>Use</button>
          </div>
          <p className="muted">Or click the map. Selected: <b>{pos.label}</b> ({pos.lat.toFixed(2)}, {pos.lon.toFixed(2)})</p>
        </div>
        <div>
          <label>Hazard
            <select value={hazard} onChange={(e) => { setHazard(e.target.value); setData(null); }}>
              <option value="heatwave">Heatwave</option>
              <option value="heavy_rainfall">Heavy rainfall</option>
              <option value="drought">Drought</option>
            </select>
          </label>
          <div className="row">
            <label>From <input type="number" min={1950} max={LAST_YEAR} value={start} onChange={(e) => setStart(+e.target.value)} /></label>
            <label>To <input type="number" min={1950} max={LAST_YEAR} value={end} onChange={(e) => setEnd(+e.target.value)} /></label>
          </div>
          <button className="primary" onClick={analyze} disabled={loading}>{loading ? "Analyzing (first run can take ~10s)…" : "Analyze"}</button>
          {data && <a className="link" href={csvUrl}>Download CSV</a>}
        </div>
      </section>

      <MapContainer center={[pos.lat, pos.lon]} zoom={5} className="map">
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
        <Marker position={[pos.lat, pos.lon]} />
        <ClickPicker onPick={(lat, lon) => setPos({ lat, lon, label: "Map pin" })} />
      </MapContainer>

      {error && <div className="error">{error}</div>}

      {data && (
        <>
          <section className="panel insight">
            <h2>{data.insight.headline}</h2>
            <p>{data.insight.detail}</p>
            <ul>{data.insight.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>
            <p className="muted">
              Definition: {data.definition} Threshold: {data.threshold.min === data.threshold.max ? data.threshold.min : `${data.threshold.min}–${data.threshold.max}`} {data.threshold.unit}.
              Source: {data.source}. {data.cached ? "Served from database cache." : "Freshly computed."}
              {data.quality.years_excluded.length > 0 && ` Years excluded (low data coverage): ${data.quality.years_excluded.join(", ")}.`}
              {` Cleaning: ${data.quality.gaps_interpolated} gaps filled, ${data.quality.implausible_removed + data.quality.spikes_removed} outliers removed, ${data.quality.still_missing} days still missing.`}
            </p>
          </section>

          <section className="panel"><h3>{m.days_label} per year</h3><Chart type="bar" data={daysChart} /></section>
          <div className="grid2">
            <section className="panel"><h3>Frequency &amp; duration</h3>
              <Chart type="bar" data={eventChart} options={{ scales: { y: { beginAtZero: true }, y1: { position: "right", beginAtZero: true, grid: { drawOnChartArea: false } } } }} />
            </section>
            <section className="panel"><h3>Intensity</h3><Chart type="line" data={intensityChart} /></section>
          </div>

          <section className="panel">
            <h3>Longest events</h3>
            <table>
              <thead><tr><th>Start</th><th>End</th><th>{m.duration_unit}</th><th>{m.peak_label}</th><th>{m.intensity_label}</th></tr></thead>
              <tbody>{data.top_events.map((e, i) => (
                <tr key={i}><td>{e.start}</td><td>{e.end}</td><td>{e.duration}</td><td>{e.peak}</td><td>{e.intensity}</td></tr>
              ))}</tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
