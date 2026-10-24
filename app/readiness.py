"""Readiness score (0-100) and a backtest against recorded 'off' episodes.

Each morning compares you with your own trailing 28-day baseline (today excluded):
  resting HR above baseline, HRV below baseline, 3-night sleep debt, training load spike (7-day vs
  4-week average), stress above baseline, low overnight body-battery charge, and the daily feel score
  when logged. Each signal costs points; 100 = nothing off.
"""
import datetime as dt, statistics as st, yaml
import data

W = {"rhr": 9, "hrv": 9, "sleep_debt_h": 9, "load": 35, "stress": 4, "bb": 4, "feel": 8}
BANDS = {"green": 70, "amber": 50}
NOISE = 0.5   # ignore wobble within half a standard deviation of your baseline   # >=70 green, 50-69 amber, <50 red

def _hrs(s):
    try: h, m = str(s).rstrip("m").split("h"); return int(h) + int(m) / 60
    except Exception: return None

def _z(v, hist):
    hist = [h for h in hist if h is not None]
    if v is None or len(hist) < 7: return None
    sd = st.pstdev(hist) or 1.0
    return (v - st.mean(hist)) / sd

def series():
    S = data.summary()
    E = {d["date"]: d for d in data.energy()["days"]}
    ref = data.reference()
    load = [sum(s["kcal"] for s in (E.get(d["date"]) or {}).get("sessions", []) if s["type"] != "walk") for d in S]
    out = []
    for i, d in enumerate(S):
        r = d.get("recovery") or {}
        base = S[max(0, i - 28): i]
        g = lambda k: [(b.get("recovery") or {}).get(k) for b in base]
        parts = {}
        z = _z(r.get("rhr"), g("rhr"));            parts["rhr"] = max(0, z - NOISE) * W["rhr"] if z is not None else None
        z = _z(r.get("hrv_ms"), g("hrv_ms"));      parts["hrv"] = max(0, -z - NOISE) * W["hrv"] if z is not None else None
        nights = [_hrs((S[j].get("recovery") or {}).get("sleep")) for j in range(max(0, i - 2), i + 1)]
        nights = [n for n in nights if n is not None]
        # sleep debt against YOUR normal (28-day median), not the 7h30 target: chronic shortfall would otherwise
        # sink every day and hide the dips. The target itself is tracked separately on the sleep chart.
        hist = [_hrs((b.get("recovery") or {}).get("sleep")) for b in base]; hist = [h for h in hist if h]
        norm = st.median(hist) if len(hist) >= 7 else ref.get("sleep_hours_min", 7.5)
        debt = sum(max(0, norm - n - 0.5) for n in nights)   # 30 min tolerance per night
        parts["sleep_debt_h"] = debt * W["sleep_debt_h"] if nights else None
        acute = sum(load[max(0, i - 6): i + 1]); chronic = sum(load[max(0, i - 27): i + 1]) / 4
        ratio = acute / chronic if chronic > 300 and i >= 27 else None   # needs 4 weeks of history, or a new user's first week reads as a load spike
        parts["load"] = max(0, ratio - 1.2) * W["load"] if ratio is not None else None
        z = _z(r.get("stress_avg"), g("stress_avg")); parts["stress"] = max(0, z - NOISE) * W["stress"] if z is not None else None
        z = _z(r.get("body_battery"), g("body_battery")); parts["bb"] = max(0, -z - NOISE) * W["bb"] if z is not None else None
        feel = (d.get("feel") or {}).get("overall")
        parts["feel"] = max(0, 3 - feel) * W["feel"] if feel else None
        known = {k: v for k, v in parts.items() if v is not None}
        score = round(max(0, 100 - sum(known.values()))) if len(known) >= 3 else None
        band = None if score is None else "green" if score >= BANDS["green"] else "amber" if score >= BANDS["amber"] else "red"
        top = sorted(((v, k) for k, v in known.items() if v >= 3), reverse=True)[:2]
        out.append({"date": d["date"], "score": score, "band": band, "parts": {k: round(v, 1) for k, v in known.items()},
                    "drivers": [k for _, k in top], "sleep_debt_h": round(debt, 1) if nights else None, "load_ratio": round(ratio, 2) if ratio else None})
    return out

def episodes():
    try: return [{**e, "start": str(e["start"]), "end": str(e["end"])} for e in yaml.safe_load((data.ROOT / "measurements" / "episodes.yaml").read_text())]
    except Exception: return []

def backtest(threshold=None):
    """For each episode: lowest score in the 2 days before it starts. Compare with how often ordinary days score that low."""
    ser = [s for s in series() if s["score"] is not None]
    by = {s["date"]: s for s in ser}
    eps = episodes()
    in_ep = set()
    for e in eps:
        d = dt.date.fromisoformat(e["start"]) - dt.timedelta(days=2)
        while d <= dt.date.fromisoformat(e["end"]):
            in_ep.add(d.isoformat()); d += dt.timedelta(days=1)
    normal = [s["score"] for s in ser if s["date"] not in in_ep]
    res = []
    for e in eps:
        s0 = dt.date.fromisoformat(e["start"])
        pre = [by.get((s0 - dt.timedelta(days=k)).isoformat()) for k in (2, 1)]
        pre = [p for p in pre if p]
        low = min((p["score"] for p in pre), default=None)
        pct = round(100 * sum(1 for v in normal if v <= low) / len(normal)) if low is not None and normal else None
        res.append({**e, "pre_scores": [(p["date"], p["score"], p["drivers"]) for p in pre], "lowest_before": low,
                    "ordinary_days_as_low_pct": pct})
    thr = threshold or BANDS["amber"]
    flagged = sum(1 for r in res if r["lowest_before"] is not None and r["lowest_before"] < thr)
    false_alarm = round(100 * sum(1 for v in normal if v < thr) / len(normal)) if normal else None
    return {"threshold": thr, "episodes": res, "flagged": flagged, "of": len(res), "ordinary_days_below_pct": false_alarm,
            "ordinary_days": len(normal), "ordinary_median": st.median(normal) if normal else None}
