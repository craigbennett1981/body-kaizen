"""One health number (0-100) scored against the fit, athletic reference person in athlete.yaml (age and sex set there), plus two health ages shown side by side.
Weights are a judgement informed by the evidence (fitness and strength predict mortality most strongly),
not a validated model: use it to track change over time, not to compare with anyone else."""
import bisect, datetime as dt, json
import data, longevity

DOMAINS = [  # (key, label, weight, {marker: weight within domain})
    ("cardio_fitness", "Cardio fitness", 25, {"vo2max": 3, "rhr": 1, "hrv": 1, "aerobic_min": 1}),
    ("heart", "Heart and blood", 20, {"apob": 3, "ldl": 1, "lpa": 1, "bp_sys": 1, "bp_dia": 1, "hscrp": 1, "tg": 1, "hdl": 1}),
    ("strength", "Strength and function", 15, {"grip": 2, "sit_to_stand": 1, "one_leg_stand": 1, "smi": 1, "strength_sessions": 1}),
    ("body", "Body composition", 15, {"body_fat": 1, "visceral": 1, "waist_height": 1}),
    ("metabolic", "Metabolic", 10, {"hba1c": 2, "glucose": 1, "insulin": 1, "cgm_mean": 2, "cgm_tir": 1, "cgm_cv": 1}),
    ("sleep", "Sleep and recovery", 10, {"sleep_h": 2, "sleep_onset_sd": 1}),
    ("habits", "Daily habits", 5, {"protein_gkg": 1, "fibre": 1, "satfat_pct": 1, "steps": 1}),
]
MIN_COVERAGE = 0.4   # earlier days rest on too few inputs to plot
STALE = {"lab": 400, "inbody": 400, "manual": 400, "garmin": 21, "derived": 21, "cgm": 21}

UNMEASURED = 50   # unknown = average, no credit until measured

def _athlete():
    p = data.ROOT / "athlete.yaml"
    return (data._load(p) or {}).get("markers", {}) if p.exists() else {}

def athlete_score(a, v):
    """0 at poor, 50 at average, 100 at athlete level; linear between, capped."""
    top, avg, poor = a["top"], a["avg"], a["poor"]
    up = top > avg   # higher is better
    if (v >= top) if up else (v <= top): return 100.0
    if (v <= poor) if up else (v >= poor): return 0.0
    if (v >= avg) if up else (v <= avg): return round(50 + 50 * (v - avg) / (top - avg), 1)
    return round(50 * (v - poor) / (avg - poor), 1)

def marker_score(m, v, ref=None):
    """100 in the green band, sliding through amber (75 -> 40), red 25 -> 0. None if it can't be judged."""
    s = longevity.status(m, v, ref)
    if s == "grey": return None
    if m.get("bands") == "lab": return 100 if s == "green" else 60 if s == "amber" else 30
    if s == "green": return 100
    g, a = m.get("green") or [None, None], m.get("amber") or [None, None]
    width = None
    if a[0] is not None and a[1] is not None: width = a[1] - a[0]
    if s == "amber" and width:
        near = a[0] if (g[1] is not None and abs(a[0] - g[1]) < 1e-9) else a[1]   # edge touching green
        frac = min(1, abs(v - near) / width)
        return round(75 - 35 * frac, 1)
    if s == "amber": return 60
    if width:   # red: distance past the amber band, in amber-widths
        far = a[1] if (g[1] is not None and abs(a[0] - g[1]) < 1e-9) else a[0]
        return round(max(0, 25 - 25 * abs(v - far) / width), 1)
    return 15

def _series():
    L = longevity.compute()
    by = {m["id"]: m for m in L["markers"]}
    C = longevity.cfg()["markers"]
    hist = {}
    for k, m in by.items():
        h = [(longevity._d(d), v) for d, v in m["history"] if v is not None]
        hist[k] = ([d for d, _ in h], [v for _, v in h])
    return L, by, C, hist

def score_at(day, by, C, hist, A=None):
    A = _athlete() if A is None else A
    out, tot_w, got_w, acc = [], 0, 0, 0
    for key, label, w, mk in DOMAINS:
        sw = sum(mk.values()); parts = []
        for mid, mw in mk.items():
            m = C.get(mid)
            if not m: continue
            ds, vs = hist.get(mid, ([], []))
            i = bisect.bisect_right(ds, day) - 1
            v = vs[i] if i >= 0 and (day - ds[i]).days <= STALE.get(m.get("source"), 30) else None
            a = A.get(mid)
            if v is None: sc = None
            elif a: sc = athlete_score(a, v)
            else: sc = marker_score(m, v, (by.get(mid) or {}).get("lab_ref"))
            parts.append({"id": mid, "name": m.get("name", mid), "weight": mw, "value": v, "score": sc,
                          "used": sc if sc is not None else UNMEASURED, "assumed": sc is None,
                          "ref": {k: a[k] for k in ("top", "avg", "poor")} if a else None,
                          "date": ds[i].isoformat() if v is not None else None})
        hw = sum(p["weight"] for p in parts if not p["assumed"])
        ds_ = round(sum(p["used"] * p["weight"] for p in parts) / sw, 1)
        cov = hw / sw
        tot_w += w; got_w += w * cov; acc += ds_ * w
        out.append({"key": key, "label": label, "weight": w, "score": ds_, "coverage": round(cov, 2), "markers": parts})
    score = round(acc / tot_w, 1) if tot_w else None
    return {"score": score, "coverage": round(got_w / tot_w, 2), "domains": out}

def compute():
    L, by, C, hist = _series()
    S = data.summary()
    if not S: return {}
    first, last = longevity._d(S[0]["date"]), longevity._d(S[-1]["date"])
    A = _athlete()
    today = score_at(last, by, C, hist, A)
    history = []
    d = first
    while d <= last:
        s = score_at(d, by, C, hist, A)
        if s["score"] is not None and s["coverage"] >= MIN_COVERAGE: history.append([d.isoformat(), s["score"], s["coverage"]])
        d += dt.timedelta(days=1)
    hmap = {h[0]: h for h in history}
    def delta(days):
        t = last - dt.timedelta(days=days)
        prev = [h for h in history if h[0] <= t.isoformat()]
        if not prev or (t - longevity._d(prev[-1][0])).days > max(3, days // 10): return None
        then = score_at(longevity._d(prev[-1][0]), by, C, hist, A)
        tw = sum(dm["weight"] for dm in today["domains"]) or 1
        drivers = []
        for dn, dp in zip(today["domains"], then["domains"]):
            sw = sum(p["weight"] for p in dn["markers"]) or 1
            old = {p["id"]: p for p in dp["markers"]}
            for p in dn["markers"]:
                o = old.get(p["id"])
                if not o: continue
                c = (p["used"] - o["used"]) * dn["weight"] * p["weight"] / sw / tw
                if abs(c) >= 0.05:
                    why = ("newly measured" if o["assumed"] and not p["assumed"] else "now out of date" if p["assumed"] and not o["assumed"] else None)
                    drivers.append({"name": p["name"], "domain": dn["label"], "change": round(c, 1), "from": o["value"], "to": p["value"], "why": why})
        drivers.sort(key=lambda x: -abs(x["change"]))
        return {"from": prev[-1][1], "change": round(today["score"] - prev[-1][1], 1), "coverage_from": prev[-1][2], "date_from": prev[-1][0], "drivers": drivers[:6]}
    # biggest drags: covered markers ranked by (100 - score) x effective weight
    drags = []
    for dom in today["domains"]:
        sw = sum(p["weight"] for p in dom["markers"])
        for p in dom["markers"]:
            if p["used"] < 100:
                drags.append({"name": p["name"] + (" (not measured)" if p["assumed"] else ""), "domain": dom["label"], "score": p["used"],
                              "cost": round((100 - p["used"]) * dom["weight"] * p["weight"] / sw / 100, 1)})
    drags.sort(key=lambda x: -x["cost"])
    missing = [p["name"] for dom in today["domains"] for p in dom["markers"] if p["assumed"]]
    # what's still to measure, ranked by how much of the score it carries (its share of the total weight)
    tw = sum(dm["weight"] for dm in today["domains"]) or 1
    to_measure = []
    for dom in today["domains"]:
        sw = sum(p["weight"] for p in dom["markers"]) or 1
        for p in dom["markers"]:
            if not p["assumed"]: continue
            ds = hist.get(p["id"], ([], []))[0]
            to_measure.append({"name": p["name"], "domain": dom["label"], "share": round(100 * dom["weight"] * p["weight"] / sw / tw, 1),
                               "last": ds[-1].isoformat() if ds else None})
    to_measure.sort(key=lambda x: -x["share"])
    # ages
    fa = None
    fp = data.ROOT / "imports" / "garmin" / "fitness_age.json"
    if fp.exists():
        fah = json.loads(fp.read_text())
        if fah:
            d_, v_ = sorted(fah.items())[-1]
            fa = {"age": round(float(v_["fitnessAge"]), 1), "date": d_, "achievable": v_.get("achievableFitnessAge"),
                  "history": [[k, round(float(v["fitnessAge"]), 1)] for k, v in sorted(fah.items())]}
    if fa is None:
        for p in reversed(data.day_files()):
            f = (data._load(p) or {}).get("fitness") or {}
            if f.get("fitness_age"): fa = {"age": f["fitness_age"], "date": str(data._load(p)["date"])}; break
    ph = L.get("phenoage") or {}
    prof = (data._load(data.ROOT / "athlete.yaml") or {}) if (data.ROOT / "athlete.yaml").exists() else {}
    return {"as_of": last.isoformat(), **today, "history": history, "athlete": {"age": prof.get("age"), "sex": prof.get("sex")},
            "delta": {"week": delta(7), "month": delta(30), "year": delta(365)},
            "drags": drags[:5], "missing": missing, "to_measure": to_measure,
            "ages": {"actual": L["profile"].get("age"), "fitness_age": fa,
                     "phenoage": {"age": ph.get("phenoage"), "date": ph.get("date"), "missing": len(ph.get("missing") or [])}}}
