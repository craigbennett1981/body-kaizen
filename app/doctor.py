"""Everything a GP visit needs on one printable page: labs side by side, BP, body composition, recent trends, untested markers."""
import datetime as dt, statistics as st
import data, longevity

def questions(by):
    """Questions for the appointment, only where the data gives a reason to ask."""
    v = lambda k: (by.get(k) or {}).get("value"); bad = lambda k: (by.get(k) or {}).get("status") in ("amber", "red")
    q = []
    if v("ldl") is not None:
        q.append(f"What is my 10-year cardiovascular risk, and so my LDL-C target? LDL-C is {v('ldl')} mmol/L"
                 + (f" (ApoB {v('apob')} g/L)." if v("apob") is not None else "."))
    if v("lpa") is None: q.append("Is a one-off Lp(a) test worth adding to the next blood test?")
    if bad("hscrp"): q.append(f"hs-CRP was {v('hscrp')} mg/L. Retest when well, or investigate?")
    if bad("b12"): q.append(f"B12 is outside the range ({v('b12')}). Should I change any supplements?")
    q.append("Can the next blood test add anything missing from the 'Not yet tested' list below?")
    return q

def report():
    C = longevity.cfg(); M = C["markers"]; L = longevity.compute()
    labs = sorted(longevity._yaml("labs.yaml"), key=lambda d: str(d["date"]))
    dates = [str(d["date"])[:10] for d in labs]
    rows = {}
    for i, dr in enumerate(labs):
        for r in dr.get("results") or []:
            k = r["marker"]; m = M.get(k, {})
            row = rows.setdefault(k, {"id": k, "name": m.get("name", k), "unit": r.get("unit", ""), "cat": m.get("cat"), "values": [None] * len(labs), "flags": [None] * len(labs)})
            row["values"][i] = r["value"]; row["flags"][i] = r.get("flag")
            lo, hi = r.get("ref_low"), r.get("ref_high")
            row["ref"] = (f"{lo}–{hi}" if lo is not None and hi is not None else f"< {hi}" if hi is not None else f"> {lo}" if lo is not None else "")
    order = list(M)
    lab_rows = sorted(rows.values(), key=lambda r: order.index(r["id"]) if r["id"] in order else 999)
    by = {m["id"]: m for m in L["markers"]}
    for r in lab_rows: r["status"] = by.get(r["id"], {}).get("status")
    # recent trends: last 30 days with data
    S = data.summary(); today = dt.date.fromisoformat(S[-1]["date"]) if S else data.bkenv.today()
    recent = [d for d in S if (today - dt.date.fromisoformat(d["date"])).days < 30]
    def avg(vals, nd=1):
        v = [x for x in vals if x is not None]
        return (round(st.mean(v), nd), len(v)) if v else (None, 0)
    def hrs(s):
        try: h, m = str(s).replace("m", "").split("h"); return int(h) + int(m) / 60
        except Exception: return None
    wts = [(d["date"], d["weight"]["kg"]) for d in S if d.get("weight") and d["weight"].get("fasted") is not False]
    gym = sum(1 for d in recent for e in (data._jsonable(data._load(data.ROOT / "days" / d["date"][:4] / f"{d['date']}.yaml")).get("exercise") or []) if e.get("type") == "gym")
    runs = sum(1 for d in recent for e in (data._jsonable(data._load(data.ROOT / "days" / d["date"][:4] / f"{d['date']}.yaml")).get("exercise") or []) if e.get("type") in ("run", "ruck", "swim"))
    trends = [
        ("Resting heart rate", *avg([(d.get("recovery") or {}).get("rhr") for d in recent]), "bpm"),
        ("Overnight HRV", *avg([(d.get("recovery") or {}).get("hrv_ms") for d in recent]), "ms"),
        ("Sleep", *avg([hrs((d.get("recovery") or {}).get("sleep")) for d in recent]), "h/night"),
        ("Steps", *avg([d.get("steps") for d in recent], 0), "/day"),
        ("Protein", *avg([(d.get("totals") or {}).get("protein_g") for d in recent if d.get("status") == "complete"], 0), "g/day"),
        ("Saturated fat", *avg([(d.get("totals") or {}).get("satfat_g") for d in recent if d.get("status") == "complete"], 0), "g/day"),
        ("Calories", *avg([(d.get("totals") or {}).get("kcal") for d in recent if d.get("status") == "complete"], 0), "kcal/day"),
    ]
    bp = data.bp_readings()
    bp30 = [b for b in bp if (today - dt.date.fromisoformat(b["date"])).days < 30] or bp
    return {
        "profile": C.get("profile", {}), "generated": data.bkenv.today().isoformat(), "as_of": S[-1]["date"] if S else None,
        "lab_dates": dates, "labs": lab_rows,
        "bp": {"readings": bp, "avg_sys": round(st.mean(b["sys"] for b in bp30)) if bp30 else None, "avg_dia": round(st.mean(b["dia"] for b in bp30)) if bp30 else None,
               "n": len(bp30), "category": data.bp_category(round(st.mean(b["sys"] for b in bp30)), round(st.mean(b["dia"] for b in bp30))) if bp30 else None},
        "inbody": longevity._yaml("inbody.yaml"),
        "weight": {"first": wts[0] if wts else None, "last": wts[-1] if wts else None},
        "trends": [{"name": n, "value": v, "n": k, "unit": u} for n, v, k, u in trends],
        "training": {"gym_30d": gym, "cardio_30d": runs},
        "untested": [b for b in L["blood_checklist"] if b["reason"] == "never tested"],
        "name": data.bkenv.profile().get("name"),
        "lab_names": sorted({str(d["lab"]) for d in labs if d.get("lab")}),
        "questions": questions(by),
    }
