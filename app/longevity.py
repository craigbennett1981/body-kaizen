"""Long-term markers: compute each marker in markers.yaml from the repo's data, with history, status and due dates."""
import datetime as dt, statistics as st
import data

def cfg():
    return data._load(data.ROOT / "markers.yaml")

def _yaml(name):
    p = data.ROOT / "measurements" / name
    return (data._jsonable(data._load(p)) or []) if p.exists() else []

def _d(s): return dt.date.fromisoformat(str(s)[:10])

def _mins_from_noon(iso):
    """Clock time as minutes after 12:00, so 23:30 and 00:30 are 60 apart (sleep onset straddles midnight)."""
    t = dt.datetime.fromisoformat(iso); m = t.hour * 60 + t.minute
    return (m - 720) % 1440

def _hrs(s):
    try: h, m = str(s).rstrip("m").split("h"); return int(h) + int(m) / 60
    except Exception: return None

def _roll(dates, values, win, fn=st.mean, minn=3, own=True):
    """Rolling stat over the last `win` days at each date. Returns [(date, value)].
    own=True: only emit on days that have their own value, so a stale window never looks current."""
    out = []
    for i, d in enumerate(dates):
        if own and values[i] is None: continue
        lo = _d(d) - dt.timedelta(days=win - 1)
        w = [values[j] for j in range(0, i + 1) if values[j] is not None and _d(dates[j]) >= lo]
        if len(w) >= minn: out.append((d, fn(w)))
    return out

def status(m, v, ref=None):
    """green / amber / red / grey for a value against a marker's bands."""
    if v is None: return "grey"
    if m.get("bands") == "none": return "grey"
    if m.get("bands") == "lab":
        if not ref: return "grey"
        lo, hi = ref
        if (lo is None or v >= lo) and (hi is None or v <= hi):
            c = m.get("contested")
            if c and not ((c[0] is None or v >= c[0]) and (c[1] is None or v <= c[1])): return "amber"
            return "green"
        return "red"
    inside = lambda b: b and (b[0] is None or v >= b[0]) and (b[1] is None or v < b[1])   # lower inclusive, upper exclusive
    g, a = m.get("green"), m.get("amber")
    if g and inside(g):
        c = m.get("contested")
        if c and not ((c[0] is None or v >= c[0]) and (c[1] is None or v <= c[1])): return "amber"   # never red for a contested band
        return "green"
    if a and inside(a): return "amber"
    return "red" if (g or a) else "grey"

def compute():
    C = cfg(); M = C["markers"]; prof = C.get("profile", {})
    S = data.summary()
    days = [d["date"] for d in S]
    det = {d["date"]: data._jsonable(data._load(p)) for d, p in zip(S, data.day_files())}
    series = {}
    # ---- garmin / daily derived ----
    vo2 = [(d, (det[d].get("fitness") or {}).get("vo2max")) for d in days]
    series["vo2max"] = [(d, v) for d, v in vo2 if v]
    rhr = [(d.get("recovery") or {}).get("rhr") for d in S]
    series["rhr"] = [(d, round(v, 1)) for d, v in _roll(days, rhr, 7)]
    sl = [_hrs((d.get("recovery") or {}).get("sleep")) for d in S]
    series["sleep_h"] = [(d, round(v, 2)) for d, v in _roll(days, sl, 14, minn=7)]
    onset = [_mins_from_noon((det[d].get("recovery") or {}).get("sleep_start")) if (det[d].get("recovery") or {}).get("sleep_start") else None for d in days]
    wake = [_mins_from_noon((det[d].get("recovery") or {}).get("sleep_end")) if (det[d].get("recovery") or {}).get("sleep_end") else None for d in days]
    series["sleep_onset_sd"] = [(d, round(v)) for d, v in _roll(days, onset, 14, st.pstdev, minn=7)]
    series["wake_sd"] = [(d, round(v)) for d, v in _roll(days, wake, 14, st.pstdev, minn=7)]
    hrv = [(d.get("recovery") or {}).get("hrv_ms") for d in S]
    h7 = dict(_roll(days, hrv, 7)); h60 = dict(_roll(days, hrv, 60, minn=14)); h60sd = dict(_roll(days, hrv, 60, st.pstdev, minn=14))
    series["hrv"] = [(d, round(h7[d], 1)) for d in days if d in h7]
    hrv_z = next(((round((h7[d] - h60[d]) / (h60sd[d] or 1), 2)) for d in reversed(days) if d in h7 and d in h60), None)
    series["steps"] = [(d, round(v)) for d, v in _roll(days, [d.get("steps") for d in S], 30, minn=7)]
    aer = [((det[d].get("intensity_min") or {}).get("moderate", 0) + 2 * (det[d].get("intensity_min") or {}).get("vigorous", 0)) if det[d].get("intensity_min") else None for d in days]
    series["aerobic_min"] = [(d, round(v)) for d, v in _roll(days, aer, 7, sum, minn=5)]
    gym = [sum(1 for e in det[d].get("exercise") or [] if e.get("type") == "gym") for d in days]
    gym_min = [sum(e.get("duration_min") or 50 for e in det[d].get("exercise") or [] if e.get("type") == "gym") for d in days]
    series["strength_sessions"] = [(d, v) for d, v in _roll(days, gym, 7, sum, minn=1, own=False)]
    series["strength_min"] = [(d, round(v)) for d, v in _roll(days, gym_min, 7, sum, minn=1, own=False)]
    # ---- nutrition (complete days only) ----
    comp = [d if (d.get("status") == "complete" and d.get("totals")) else None for d in S]
    wts = [(d.get("weight") or {}).get("kg") if (d.get("weight") or {}).get("fasted") is not False else None for d in S]
    w7 = dict(_roll(days, wts, 7, minn=1, own=False)); w_last = None; wmap = {}
    for d in days:
        if d in w7: w_last = w7[d]
        wmap[d] = w_last
    gkg = [(c["totals"]["protein_g"] / wmap[c["date"]]) if c and wmap.get(c["date"]) else None for c in comp]
    series["protein_gkg"] = [(d, round(v, 2)) for d, v in _roll(days, gkg, 7, minn=3)]
    series["fibre"] = [(d, round(v)) for d, v in _roll(days, [c["totals"]["fibre_g"] if c else None for c in comp], 7, minn=3)]
    sfp = [(9 * c["totals"]["satfat_g"] / c["totals"]["kcal"] * 100) if c and c["totals"]["kcal"] else None for c in comp]
    series["satfat_pct"] = [(d, round(v, 1)) for d, v in _roll(days, sfp, 7, minn=3)]
    # ---- body / inbody ----
    ib = _yaml("inbody.yaml")
    for k, f in (("body_fat", "pbf_pct"), ("visceral", "visceral_level"), ("smm", "smm_kg"), ("phase_angle", "phase_angle"), ("smi", "smi"), ("ecw_ratio", "ecw_ratio")):
        series[k] = [(b["date"], b[f]) for b in ib if b.get(f) is not None]
    # ---- manual tests ----
    tests = _yaml("tests.yaml")
    series["grip"] = [(t["date"], max(t.get("left_kg") or 0, t.get("right_kg") or 0, t.get("kg") or 0)) for t in tests if t.get("test") == "grip"]   # kg = best hand when only one figure is given
    series["sit_to_stand"] = [(t["date"], t["reps"]) for t in tests if t.get("test") == "sit_to_stand"]
    series["one_leg_stand"] = [(t["date"], t["seconds"]) for t in tests if t.get("test") == "one_leg_stand"]
    series["waist_height"] = [(t["date"], round(t["cm"] / prof.get("height_cm", 180), 3)) for t in tests if t.get("test") == "waist"]
    # ---- blood pressure: 30-day average at each reading ----
    bp = data.bp_readings()
    for k in ("sys", "dia"):
        pts = []
        for b in bp:
            w = [x[k] for x in bp if 0 <= (_d(b["date"]) - _d(x["date"])).days < 30]
            pts.append((b["date"], round(st.mean(w))))
        series[f"bp_{k}"] = pts
    # ---- labs ----
    labs = _yaml("labs.yaml"); lab_ref = {}
    for draw in labs:
        vals = {}
        for r in draw.get("results") or []:
            series.setdefault(r["marker"], []).append((draw["date"], r["value"])); vals[r["marker"]] = r["value"]
            lab_ref[r["marker"]] = (r.get("ref_low"), r.get("ref_high"))
        if "total_chol" in vals and "hdl" in vals:   # derived per draw
            series.setdefault("non_hdl", []).append((draw["date"], round(vals["total_chol"] - vals["hdl"], 2)))
        if "glucose" in vals and "insulin" in vals:
            series.setdefault("homa_ir", []).append((draw["date"], round(vals["glucose"] * vals["insulin"] / 22.5, 2)))
    # ---- CGM (FreeStyle Libre): 14-day rolling over daily stats ----
    try:
        import glucose
        gs = glucose.daily_series()
        gd = [d for d, _ in gs]
        for key, f in (("cgm_mean", "mean"), ("cgm_tir", "tir"), ("cgm_cv", "cv")):
            series[key] = [(d, round(v, 1)) for d, v in _roll(gd, [s[f] for _, s in gs], 14, minn=3)]
    except Exception as e:
        print("glucose series:", e, flush=True)
    ph = phenoage(labs, prof)
    series["phenoage_gap"] = [(h["date"], h["gap"]) for h in ph["history"]]
    # ---- assemble ----
    today = dt.date.fromisoformat(days[-1]) if days else data.bkenv.today()
    out = []
    for key, m in M.items():
        pts = sorted(series.get(key, []), key=lambda x: str(x[0]))
        last = pts[-1] if pts else None
        val = last[1] if last else None
        stt = status(m, val, lab_ref.get(key))
        due = None
        if (m.get("interval_days") or m.get("once")) and m.get("source") in ("manual", "lab", "inbody", "derived"):
            if last and not m.get("once"):
                d_ = _d(last[0]) + dt.timedelta(days=m["interval_days"]); due = {"date": d_.isoformat(), "days": (d_ - today).days}
            elif not last:
                due = {"date": None, "days": None, "never": True}
        out.append({"id": key, **{k: m.get(k) for k in ("name", "unit", "cat", "source", "green", "amber", "contested", "note", "verify", "once", "interval_days", "bands")},
                    "value": val, "date": last[0] if last else None, "status": stt, "due": due,
                    "history": [[str(d), v] for d, v in pts][-200:], "lab_ref": lab_ref.get(key),
                    **({"z": hrv_z} if key == "hrv" else {})})
    counts = {s: sum(1 for o in out if o["status"] == s) for s in ("green", "amber", "red", "grey")}
    due_list = sorted([o for o in out if o["due"]], key=lambda o: (o["due"]["days"] is not None, o["due"]["days"] if o["due"]["days"] is not None else -1))
    return {"profile": prof, "levers": C.get("levers", []), "categories": C.get("categories", {}), "markers": out, "counts": counts,
            "next_due": [{"id": o["id"], "name": o["name"], **o["due"]} for o in due_list[:3]], "as_of": days[-1] if days else None,
            "phenoage": ph, "blood_checklist": blood_checklist(out)}


# ---------------- PhenoAge (Levine et al. 2018, Aging 10:573) ----------------
# SI-unit coefficients. CRP enters as ln(mg/dL), so the lab's mg/L is divided by 10.
PHENO = [("albumin", -0.0336), ("creatinine", 0.0095), ("glucose", 0.1953), ("hscrp", 0.0954), ("lymph_pct", -0.0120),
         ("mcv", 0.0268), ("rdw", 0.3306), ("alp", 0.00188), ("wbc", 0.0554)]
PHENO_WINDOW = 30   # all nine inputs must come from draws within this many days of each other

def phenoage_calc(v, age):
    import math
    x = -19.907 + 0.0804 * age
    for k, c in PHENO:
        val = v[k]
        if k == "hscrp": val = math.log(max(val, 0.01) / 10)
        x += c * val
    g = 0.0076927
    mort = 1 - math.exp(-math.exp(x) * (math.exp(120 * g) - 1) / g)
    return round(141.50225 + math.log(-0.00553 * math.log(1 - mort)) / 0.090165, 1)

def phenoage(labs, prof):
    """Latest PhenoAge where all nine inputs fall within PHENO_WINDOW days; otherwise what's missing."""
    pts = {k: sorted(((_d(dr["date"]), r["value"]) for dr in labs for r in dr.get("results") or [] if r["marker"] == k)) for k, _ in PHENO}
    have = [k for k in pts if pts[k]]
    missing = [k for k, _ in PHENO if not pts[k]]
    res = {"inputs": [k for k, _ in PHENO], "missing": missing, "window_days": PHENO_WINDOW, "history": []}
    born = prof.get("born"); age0 = prof.get("age")
    for anchor in sorted({d for k in have for d, _ in pts[k]}):
        v, ds = {}, []
        for k, _ in PHENO:
            near = [(d, x) for d, x in pts[k] if abs((d - anchor).days) <= PHENO_WINDOW]
            if not near: break
            d, x = min(near, key=lambda p: abs((p[0] - anchor).days)); v[k] = x; ds.append(d)
        else:
            if (max(ds) - min(ds)).days > PHENO_WINDOW: continue
            age = ((anchor - _d(born)).days / 365.25) if born else age0
            if age is None: continue
            pa = phenoage_calc(v, age)
            res["history"].append({"date": max(ds).isoformat(), "phenoage": pa, "age": round(age, 1), "gap": round(pa - age, 1)})
    if res["history"]: res.update(res["history"][-1])
    return res

# ---------------- next blood test checklist ----------------
WHY = {
    "lpa": "Once in a lifetime. Mostly genetic and sets how hard to push ApoB.",
    "apob": "Your main cardiovascular lever. Recheck to see whether diet changes are working.",
    "hba1c": "Three-month average glucose.",
    "glucose": "Needed with insulin for HOMA-IR, and an input to PhenoAge.",
    "insulin": "Fasting insulin shows insulin resistance years before glucose moves.",
    "hscrp": "Inflammation marker. A cold or hard training can raise it, so test when you've been well for 2–4 weeks.",
    "creatinine": "Kidney function, and a PhenoAge input. Tell the lab if you take creatine.",
    "egfr": "Kidney function, usually reported with creatinine.",
    "cystatin_c": "Kidney function that isn't skewed by muscle mass.",
    "albumin": "Liver and nutrition status, and a PhenoAge input.",
    "alp": "Liver and bone, and a PhenoAge input.",
    "alt": "ALT, AST, GGT and ALP. ALP is a PhenoAge input; GGT is sensitive to alcohol.",
    "wbc": "Full blood count. White cells, lymphocyte %, MCV and RDW are four PhenoAge inputs.",
    "lymph_pct": None, "mcv": None, "rdw": None,
    "uric_acid": "Linked to blood pressure and metabolic health.",
    "vitd": "Keep it in range; recheck yearly.", "b12": "Above range is usually from supplements: tell your doctor what you take. Recheck yearly.",
    "folate": "Pairs with B12 and homocysteine.", "homocysteine": "Linked to B12 and folate status and to cardiovascular risk.",
    "omega3_index": "Optional finger-prick test.",
    "total_chol": "Total, LDL, HDL and triglycerides. Ask for it with ApoB.", "ldl": None, "hdl": None, "tg": None, "tc_hdl_ratio": None,
}
GROUP = {"total_chol": "lipid panel", "ldl": "lipid panel", "hdl": "lipid panel", "tg": "lipid panel", "tc_hdl_ratio": "lipid panel",
         "wbc": "full blood count", "lymph_pct": "full blood count", "mcv": "full blood count", "rdw": "full blood count",
         "alt": "liver panel", "ast": "liver panel", "ggt": "liver panel", "alp": "liver panel"}

def blood_checklist(markers, horizon=45):
    """Lab markers never tested, overdue, or due within `horizon` days, grouped the way you'd ask for them."""
    rows, seen = [], set()
    for o in markers:
        if o.get("source") != "lab" or not o.get("due"): continue
        dd = o["due"]
        if not (dd.get("never") or (dd["days"] is not None and dd["days"] <= horizon) or o["status"] in ("red", "amber")): continue
        g = GROUP.get(o["id"])
        if g and g in seen: continue
        if g: seen.add(g)
        rows.append({"id": o["id"], "name": g.capitalize() if g else o["name"], "why": WHY.get(o["id"]) or "",
                     "reason": "never tested" if dd.get("never") else ("off target" if o["status"] == "red" else ("near target" if o["status"] == "amber" else ("overdue" if dd["days"] < 0 else f"due in {dd['days']} days"))),
                     "pheno": o["id"] in dict(PHENO) or g in ("full blood count", "liver panel"), "last": o.get("date")})
    order = {"never tested": 0, "off target": 1, "overdue": 2, "near target": 3}
    return sorted(rows, key=lambda r: (order.get(r["reason"], 4), not r["pheno"]))
