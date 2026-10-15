"""Trend statistics: OLS regression, Mann-Kendall + Sen's slope, rolling mean, plain-language insight."""
import math
import numpy as np
from scipy import stats


def linear(x, y) -> dict:
    r = stats.linregress(x, y)
    return {"slope": float(r.slope), "intercept": float(r.intercept),
            "p_value": float(r.pvalue), "r2": float(r.rvalue ** 2)}


def mann_kendall(y) -> dict:
    y = np.asarray(y, float)
    n = len(y)
    s = sum(np.sign(y[j] - y[i]) for i in range(n - 1) for j in range(i + 1, n))
    _, counts = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in counts)) / 18
    z = 0.0 if var == 0 or s == 0 else (s - np.sign(s)) / math.sqrt(var)
    p = float(2 * (1 - stats.norm.cdf(abs(z))))
    slopes = [(y[j] - y[i]) / (j - i) for i in range(n - 1) for j in range(i + 1, n)]
    direction = "increasing" if (p < 0.05 and z > 0) else "decreasing" if (p < 0.05 and z < 0) else "no significant trend"
    return {"z": float(z), "p_value": p, "sen_slope": float(np.median(slopes)), "direction": direction}


def rolling_mean(values: list[float], window: int = 5) -> list[float | None]:
    out = []
    for i in range(len(values)):
        lo, hi = max(0, i - window // 2), min(len(values), i + window // 2 + 1)
        out.append(round(float(np.mean(values[lo:hi])), 2) if hi - lo >= 3 else None)
    return out


def summarize(annual: list[dict], meta: dict) -> tuple[dict, dict]:
    """Adds days_roll5 / days_fit to annual rows (in place); returns (trend, insight)."""
    for a, r in zip(annual, rolling_mean([a["days"] for a in annual])):
        a["days_roll5"] = r
        a["days_fit"] = None
    valid = [a for a in annual if a["valid"]]
    if len(valid) < 10:
        return {}, {"headline": "Not enough complete years (need at least 10) for a trend.",
                    "detail": "", "caveats": []}
    x = [a["year"] for a in valid]
    y = [a["days"] for a in valid]
    lin, mk = linear(x, y), mann_kendall(y)
    for a in annual:
        a["days_fit"] = round(max(0.0, lin["intercept"] + lin["slope"] * a["year"]), 2)

    unit = meta["per_year_unit"]
    k = min(10, len(valid) // 2)
    first, last = float(np.mean(y[:k])), float(np.mean(y[-k:]))
    span1, span2 = f"{x[0]}-{x[k-1]}", f"{x[-k]}-{x[-1]}"
    if first == 0:
        change = f"from none to {last:.1f} {unit}" if last > 0 else "(none in either period)"
    else:
        change = f"{(last - first) / first * 100:+.0f}% ({first:.1f} -> {last:.1f} {unit})"
    sig = (f"statistically significant (Mann-Kendall p={mk['p_value']:.3f})" if mk["p_value"] < 0.05
           else f"not statistically significant (Mann-Kendall p={mk['p_value']:.2f})")
    headline = f"{meta['days_label']} per year changed {change}, comparing {span1} with {span2}."
    detail = (f"The trend is {sig}. Sen's slope: {mk['sen_slope']:+.2f} {unit}; "
              f"OLS slope: {lin['slope']:+.2f} {unit} (R2={lin['r2']:.2f}).")
    return {"linear": lin, "mann_kendall": mk, "years_used": len(valid)}, \
           {"headline": headline, "detail": detail, "caveats": meta["caveats"]}
