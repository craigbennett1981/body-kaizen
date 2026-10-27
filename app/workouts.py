"""One view per workout: Hevy lifts with volume and change vs the last time, alongside Garmin's numbers
(duration, HR, calories, zones, training effect, body-battery cost) and the HR trace with detected efforts."""
import datetime as dt, json, re, statistics as st
import data

SET_KG = re.compile(r"^w?([\d.]+)x(\d+)$")
SET_CARRY = re.compile(r"^w?([\d.]+)kg@(\d+)m$")
SET_HOLD = re.compile(r"^w?(\d+)s$")

def _sets(sets):
    out = []
    for s in sets or []:
        s = str(s); warm = s.startswith("w")
        m, c, h = SET_KG.match(s), SET_CARRY.match(s), SET_HOLD.match(s)
        if m: out.append({"kg": float(m.group(1)), "reps": int(m.group(2)), "warmup": warm, "raw": s})
        elif c: out.append({"kg": float(c.group(1)), "metres": int(c.group(2)), "warmup": warm, "raw": s})
        elif h: out.append({"secs": int(h.group(1)), "warmup": warm, "raw": s})
        else: out.append({"raw": s, "warmup": warm})
    return out

def _lift_stats(sets):
    ss = [x for x in _sets(sets) if not x["warmup"]]
    vol = sum(x["kg"] * x["reps"] for x in ss if "reps" in x)
    reps = sum(x.get("reps", 0) for x in ss)
    metres = sum(x.get("metres", 0) for x in ss)
    e1 = max((x["kg"] * (1 + x["reps"] / 30) for x in ss if "reps" in x), default=None)
    top = max((x["kg"] for x in ss if "kg" in x), default=None)
    return {"sets": len(ss), "reps": reps, "volume": round(vol), "metres": metres or None, "e1rm": round(e1, 1) if e1 else None, "top_kg": top}

ABBR = {"rdl": "RDL", "db": "DB"}
def _nice(ex):
    w = ex.split("-")
    return " ".join(ABBR.get(x, x.capitalize() if i == 0 else x) for i, x in enumerate(w))

def _sessions():
    out = []
    for p in data.day_files():
        d = data._jsonable(data._load(p))
        for i, e in enumerate(d.get("exercise") or []):
            if e.get("type") in (None, "walk"): continue
            out.append({"date": d["date"], "idx": i, "e": e})
    return out

def _max_hr():
    vals = [(s["e"].get("hr") or {}).get("max") for s in _sessions()]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return max([175] + vals)

def _trace(e):
    aid = e.get("garmin_id")
    if not aid: return None
    p = data.ROOT / "imports" / "garmin" / "activities" / f"{aid}.json"
    try: a = json.loads(p.read_text())
    except Exception: return None
    s = a.get("samples") or []
    if not s: return None
    t0 = s[0][0]
    pts = [[round((t - t0) / 60000, 2), hr] for t, hr, *_ in s]
    # efforts: HR peaks at least 8 bpm above the lowest point since the previous peak, 45 s or more apart
    sm = [pts[0][1]] + [round((pts[i - 1][1] + pts[i][1] + pts[i + 1][1]) / 3, 1) for i in range(1, len(pts) - 1)] + [pts[-1][1]]
    peaks, low, last_t = [], sm[0], -9
    for i in range(1, len(sm) - 1):
        low = min(low, sm[i])
        if sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and sm[i] - low >= 8 and pts[i][0] - last_t >= 0.75:
            peaks.append([pts[i][0], pts[i][1]]); low = sm[i]; last_t = pts[i][0]
    gaps = [b[0] - a[0] for a, b in zip(peaks, peaks[1:])]
    return {"points": pts, "efforts": peaks, "effort_gap_min": round(st.median(gaps), 1) if gaps else None,
            "aerobic_te": a.get("aerobic_te"), "anaerobic_te": a.get("anaerobic_te"), "te_label": a.get("te_label"),
            "body_battery_change": a.get("body_battery_change"), "summary": a.get("summary") or {}}

def _laps(e):
    """Lap table for a run: the watch's own laps when it recorded several, otherwise 1 km splits worked out from the
    speed trace, scaled to the session's distance (the treadmill belt's, when that was logged)."""
    aid = e.get("garmin_id")
    if not aid: return None
    try: a = json.loads((data.ROOT / "imports" / "garmin" / "activities" / f"{aid}.json").read_text())
    except Exception: return None
    dist_km = e.get("distance_km")
    watch = [l for l in a.get("laps") or [] if (l.get("distance_m") or 0) >= 50 and l.get("duration_s")]   # drop the stub lap from stopping the watch
    if len(watch) > 1:
        out = [{"km": round(l["distance_m"] / 1000, 2), "secs": round(l["duration_s"]), "hr_avg": l.get("hr_avg"), "hr_max": l.get("hr_max"),
                "cadence": l.get("cadence")} for l in watch]
        src = "watch laps"
    else:
        s = [x for x in a.get("samples") or [] if len(x) > 2]
        if len(s) < 60 or not any(x[2] for x in s): return None
        cum, d = [0.0], 0.0
        for i in range(1, len(s)):
            d += (s[i][2] or 0) * (s[i][0] - s[i - 1][0]) / 1000; cum.append(d)
        if d < 500: return None
        scale = (dist_km * 1000 / d) if dist_km else 1.0
        cum = [c * scale for c in cum]; total = cum[-1]
        out, start, mark = [], 0, 1000.0
        while start < len(s) - 1:
            end = next((i for i in range(start, len(s)) if cum[i] >= mark), len(s) - 1)
            seg = s[start:end + 1]; hrs = [x[1] for x in seg if x[1]]
            km = (cum[end] - cum[start]) / 1000
            if km >= 0.05:
                out.append({"km": round(km, 2), "secs": round((s[end][0] - s[start][0]) / 1000),
                            "hr_avg": round(sum(hrs) / len(hrs)) if hrs else None, "hr_max": max(hrs) if hrs else None})
            if end >= len(s) - 1: break
            start, mark = end, mark + 1000
        src = "1 km splits from the speed trace" + (" (scaled to the belt distance)" if e.get("distance_source") == "belt" else "")
    for l in out: l["pace_s"] = round(l["secs"] / l["km"]) if l["km"] else None
    full = [l for l in out if l["km"] >= 0.9]
    if full:
        f = min(full, key=lambda l: l["pace_s"]); f["fastest"] = True
    return {"source": src, "laps": out}

def _summary(s):
    e = s["e"]
    lifts = e.get("lifts") or []
    st_ = [_lift_stats(l.get("sets")) for l in lifts]
    return {"date": s["date"], "idx": s["idx"], "type": e.get("type"), "name": e.get("hevy_name") or e.get("name") or e.get("type", "").title(),
            "start": e.get("start"), "sets": sum(x["sets"] for x in st_), "volume": sum(x["volume"] for x in st_),
            "duration_min": e.get("duration_min"), "kcal": (e.get("kcal") or {}).get("total"), "hr_avg": (e.get("hr") or {}).get("avg"),
            "distance_km": e.get("distance_km"), "garmin": bool(e.get("garmin_id")), "lifts": len(lifts)}

def index():
    ss = _sessions()
    return [_summary(s) for s in reversed(ss)]

def detail(date, idx=0):
    ss = _sessions()
    pos = next((k for k, s in enumerate(ss) if s["date"] == date and s["idx"] == int(idx)), None)
    if pos is None: return None
    s = ss[pos]; e = s["e"]
    tr = data.training()
    prs = {lift: True for lift, pts in tr["lifts"].items() for p in pts if p["date"] == date and p.get("pr") and len(pts) > 1}
    prev_gym = next((x for x in reversed(ss[:pos]) if x["e"].get("type") == e.get("type")), None)
    lifts = []
    for l in e.get("lifts") or []:
        cur = _lift_stats(l.get("sets"))
        prev = None
        for x in reversed(ss[:pos]):
            hit = next((pl for pl in x["e"].get("lifts") or [] if pl["ex"] == l["ex"]), None)
            if hit: prev = {"date": x["date"], "sets_raw": hit.get("sets"), **_lift_stats(hit.get("sets"))}; break
        lifts.append({"ex": l["ex"], "name": _nice(l["ex"]), "sets_raw": l.get("sets"), "note": l.get("note"), **cur, "pr": l["ex"] in prs, "prev": prev,
                      "vol_change": (cur["volume"] - prev["volume"]) if prev and prev["volume"] else None,
                      "e1rm_change": round(cur["e1rm"] - prev["e1rm"], 1) if prev and cur["e1rm"] and prev["e1rm"] else None})
    summ = _summary(s)
    prev_summ = _summary(prev_gym) if prev_gym else None
    mx = _max_hr()
    tr_ = _trace(e)
    sm = (tr_ or {}).get("summary") or {}
    hrr = None if e.get("hrr_invalid") else ((e.get("hr") or {}).get("recovery") or sm.get("recoveryHeartRate"))
    load = sm.get("activityTrainingLoad")
    return {"session": summ, "prev": prev_summ, "lifts": lifts, "hevy": e.get("hevy"), "note": e.get("note"), "coach": e.get("coach") or [],
            "hr": e.get("hr"), "kcal": e.get("kcal"), "zones_min": e.get("zones_min"), "cadence": e.get("cadence"),
            "time": e.get("time"), "trace": tr_, "max_hr": mx, "hrr": hrr, "training_load": round(load) if load else None,
            "zone_bounds": [round(mx * f) for f in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)], "prs": sum(1 for x in lifts if x["pr"]),
            "laps": _laps(e) if e.get("type") in ("run", "walk", "ruck") else None}
