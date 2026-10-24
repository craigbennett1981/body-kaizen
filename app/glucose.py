"""FreeStyle Libre glucose: daily stats, meal responses (needs a time on the meal entry), and rolling series."""
import datetime as dt, json, statistics as st
import data

RAW = data.ROOT / "imports" / "libre"
LOW, HIGH = 3.9, 7.8          # non-diabetic target range, mmol/L
SETTLE_H = 24                 # first day of a sensor reads less accurately

def _load(day):
    p = RAW / day[:4] / f"{day}.json"
    if not p.exists(): return []
    r = json.loads(p.read_text())["readings"]
    return [(dt.datetime.fromisoformat(f"{day}T{t}"), v) for t, v in r.items()]

def readings(day, pad_h=0):
    d = dt.date.fromisoformat(day)
    out = _load(day)
    if pad_h:
        out = [x for x in _load((d - dt.timedelta(days=1)).isoformat()) if x[0] >= dt.datetime.combine(d, dt.time()) - dt.timedelta(hours=pad_h)] + out
    return sorted(out)

def first_reading():
    files = sorted(RAW.glob("*/*.json"))
    for f in files:
        r = _load(f.stem)
        if r: return min(r)[0]
    return None

def stats(rs):
    v = [x for _, x in rs]
    if len(v) < 8: return None
    m = st.mean(v); sd = st.pstdev(v)
    night = [x for t, x in rs if 3 <= t.hour < 6]
    return {"n": len(v), "mean": round(m, 2), "sd": round(sd, 2), "cv": round(sd / m * 100, 1),
            "tir": round(sum(LOW <= x <= HIGH for x in v) / len(v) * 100, 1),
            "above": round(sum(x > HIGH for x in v) / len(v) * 100, 1), "below": round(sum(x < LOW for x in v) / len(v) * 100, 1),
            "min": min(v), "max": max(v), "overnight": round(st.mean(night), 2) if len(night) >= 4 else None}

def meal_times(day):
    """Meal entries that have a time: [(time, meal, label)]."""
    p = data.ROOT / "days" / day[:4] / f"{day}.yaml"
    if not p.exists(): return []
    d = data._load(p) or {}
    out = []
    for meal, items in (d.get("meals") or {}).items():
        for e in items or []:
            t = e.get("time") or (d.get("meal_times") or {}).get(meal)
            if t: out.append((str(t)[:5], meal, e.get("raw", "")))
    # items eaten within 20 minutes of each other count as one eating event (timed from the first item)
    out.sort(key=lambda r: r[0])
    events = []
    for t, meal, raw in out:
        tm = dt.datetime.strptime(t, "%H:%M")
        if events and (tm - events[-1]["last"]).total_seconds() <= 20 * 60:
            ev = events[-1]; ev["last"] = tm; ev["raw"].append(raw)
            if meal not in ev["meals"]: ev["meals"].append(meal)
        else:
            events.append({"time": t, "last": tm, "meals": [meal], "raw": [raw]})
    return [(e["time"], " + ".join(e["meals"]), ", ".join(e["raw"])) for e in events]

def responses(day, rs):
    out = []
    for t, meal, label in meal_times(day):
        t0 = dt.datetime.fromisoformat(f"{day}T{t}")
        pre = [v for ts, v in rs if t0 - dt.timedelta(minutes=30) <= ts <= t0]
        win = [(ts, v) for ts, v in rs if t0 < ts <= t0 + dt.timedelta(minutes=150)]
        if not pre:
            out.append({"time": t, "meal": meal, "label": label, "pending": True,
                        "why": "no readings before this meal" if (not rs or rs[0][0] > t0) else "gap in readings before this meal"}); continue
        if len(win) < 4: out.append({"time": t, "meal": meal, "label": label, "pending": True, "why": "waiting for 2 hours of readings"}); continue
        base = st.mean(pre); pk_t, pk = max(win, key=lambda x: x[1])
        back = next((ts for ts, v in win if ts > pk_t and v <= base + 0.3), None)
        auc = 0.0
        for (a, va), (b, vb) in zip(win, win[1:]):
            auc += max(0, (va + vb) / 2 - base) * (b - a).total_seconds() / 3600
        out.append({"time": t, "meal": meal, "label": label, "base": round(base, 1), "peak": round(pk, 1), "rise": round(pk - base, 1),
                    "peak_min": int((pk_t - t0).total_seconds() // 60), "back_min": int((back - t0).total_seconds() // 60) if back else None,
                    "iauc": round(auc, 2)})
    return out

def day(day_):
    rs = readings(day_)
    first = first_reading()
    settle = first and rs and (min(rs)[0] - first).total_seconds() < SETTLE_H * 3600
    return {"date": day_, "unit": "mmol/L", "range": [LOW, HIGH], "readings": [[t.strftime("%H:%M"), v] for t, v in rs],
            "stats": stats(rs), "meals": responses(day_, rs), "settling": bool(settle),
            "sensor_start": first.isoformat(timespec="minutes") if first else None}

def daily_series():
    """[(date, stats)] for every day with enough readings, skipping the settling-in day."""
    first = first_reading(); out = []
    for f in sorted(RAW.glob("*/*.json")):
        rs = _load(f.stem); s = stats(rs)
        if s and not (first and (max(rs)[0] - first).total_seconds() < SETTLE_H * 3600): out.append((f.stem, s))
    return out

def status():
    p = RAW / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}

def _pct(v, q):
    v = sorted(v); k = (len(v) - 1) * q; f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)

def overview(days=14):
    """Multi-day view: daily stats, a 24-hour profile (median and percentile bands per 30 minutes), meals ranked by spike."""
    files = sorted(RAW.glob("*/*.json"))
    if not files: return {"days": [], "profile": [], "meals": [], "window": days}
    last = dt.date.fromisoformat(files[-1].stem)
    want = [(last - dt.timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    first = first_reading()
    daily, buckets, meals = [], {}, []
    for d in want:
        rs = _load(d)
        if not rs: continue
        s = stats(rs)
        settling = bool(first and (max(rs)[0] - first).total_seconds() < SETTLE_H * 3600)
        daily.append({"date": d, "n": len(rs), "settling": settling, **(s or {})})
        for t, v in rs: buckets.setdefault(t.hour * 2 + t.minute // 30, []).append(v)
        for m in responses(d, rs):
            if not m.get("pending"): meals.append({"date": d, **m})
    profile = [{"t": f"{b // 2:02d}:{30 * (b % 2):02d}", "n": len(v), "p5": round(_pct(v, .05), 2), "p25": round(_pct(v, .25), 2),
                "p50": round(_pct(v, .5), 2), "p75": round(_pct(v, .75), 2), "p95": round(_pct(v, .95), 2)}
               for b, v in sorted(buckets.items()) if len(v) >= 2]
    allv = [v for d in want for _, v in _load(d)]
    return {"window": days, "from": daily[0]["date"] if daily else want[0], "to": want[-1], "days": daily, "profile": profile,
            "overall": _overall(allv),
            "meals": sorted(meals, key=lambda m: -m["rise"]), "range": [LOW, HIGH]}

def _overall(v):
    if len(v) < 8: return None
    m = st.mean(v); sd = st.pstdev(v)
    return {"n": len(v), "mean": round(m, 2), "cv": round(sd / m * 100, 1), "tir": round(sum(LOW <= x <= HIGH for x in v) / len(v) * 100, 1),
            "gmi": round((3.31 + 0.02392 * m * MGDL_) / 1, 1)}

MGDL_ = 18.016
