export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function get(path, params) {
  const r = await fetch(`${API}${path}?${new URLSearchParams(params)}`);
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(msg);
  }
  return r.json();
}
