"""Weekly review (Monday-Sunday): adherence, averages, training, recovery, weight, and one focus for next week."""
import datetime as dt
import data

METRICS = [("kcal", "Calories"), ("protein_g", "Protein"), ("satfat_g", "Saturated fat"), ("fibre_g", "Fibre")]

def monday(d):
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return d - dt.timedelta(days=d.weekday())

def _hrs(s):
    try: h, m = str(s).rstrip("m").split("h"); return int(h) + int(m) / 60
    except Exception: return None

def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None

def week(start=None):
    S = data.summary()
    if not S: return None
    start = monday(start or S[-1]["date"]); end = start + dt.timedelta(days=6)
    days = [d for d in S if start.isoformat() <= d["date"] <= end.isoformat()]
    prev = [d for d in S if (start - dt.timedelta(days=7)).isoformat() <= d["date"] < start.isoformat()]
    comp = [d for d in days if d.get("status") == "complete" and d.get("totals")]
    status = {k: sum(1 for d in days if d.get("status") == k) for k in ("complete", "partial", "unlogged")}
    hits = {}
    for k, _ in METRICS:
        judged = [d for d in comp if (d.get("eval") or {}).get(k) and d["eval"][k]["ok"] is not None]
        hits[k] = {"hit": sum(1 for d in judged if d["eval"][k]["ok"]), "of": len(judged)}
    avgs = {k: (round(v) if v is not None and k != "satfat_g" else v) for k, v in ((k, _avg([d["totals"][k] for d in comp])) for k, _ in METRICS)}
    def wavg(ds): return _avg([d["weight"]["kg"] for d in ds if d.get("weight") and d["weight"].get("fasted") is not False])
    weight = {"avg": wavg(days), "prev_avg": wavg(prev)}
    # training
    E = {d["date"]: d for d in data.energy()["days"]}
    sessions, kcal, run_km = {}, 0, 0.0
    for d in days:
        for s in (E.get(d["date"]) or {}).get("sessions", []):
            if s["type"] != "walk": sessions[s["type"]] = sessions.get(s["type"], 0) + 1
            kcal += s["kcal"]
        for e in d.get("exercise") or []:
            if e.get("type") == "run" and e.get("distance_km"): run_km += e["distance_km"]
    prs = []
    for lift, pts in data.training()["lifts"].items():
        for p in pts:
            if start.isoformat() <= p["date"] <= end.isoformat() and p.get("pr") and len(pts) > 1:
                prs = [x for x in prs if x["lift"] != lift]   # keep only the week's best per lift (points are in date order)
                prs.append({"lift": lift, "date": p["date"], "kg": p["kg"], "reps": p.get("reps"), "metres": p.get("metres")})
    # recovery
    ref = data.reference()
    sl = [_hrs((d.get("recovery") or {}).get("sleep")) for d in days]
    recovery = {"sleep_avg_h": _avg(sl), "nights_ok": sum(1 for v in sl if v is not None and v >= ref.get("sleep_hours_min", 7.5)),
                "nights": sum(1 for v in sl if v is not None),
                "hrv_avg": _avg([(d.get("recovery") or {}).get("hrv_ms") for d in days]),
                "rhr_avg": _avg([(d.get("recovery") or {}).get("rhr") for d in days]),
                "steps_avg": (lambda v: round(v) if v is not None else None)(_avg([d.get("steps") for d in days]))}
    bp = [b for b in data.bp_readings() if start.isoformat() <= b["date"] <= end.isoformat()]
    # best / worst complete day by targets met, then by protein
    def met(d): return sum(1 for k, _ in METRICS if ((d.get("eval") or {}).get(k) or {}).get("ok"))
    ranked = sorted(comp, key=lambda d: (met(d), d["totals"]["protein_g"]))
    best = {"date": ranked[-1]["date"], "met": met(ranked[-1])} if ranked else None
    worst = {"date": ranked[0]["date"], "met": met(ranked[0])} if len(ranked) > 1 else None
    # one focus for next week: the weakest area
    focus = None
    cands = []
    if status["complete"] < 5: cands.append((status["complete"] / 7, f"Log every day: only {status['complete']} of 7 days were complete, so the numbers are guesswork."))
    for k, label in METRICS:
        h = hits[k]
        if h["of"]: cands.append((h["hit"] / h["of"], f"{label}: hit on {h['hit']} of {h['of']} logged days. Make it the one thing you fix."))
    if recovery["nights"]: cands.append((recovery["nights_ok"] / max(1, recovery["nights"]), f"Sleep: {recovery['nights_ok']} of {recovery['nights']} nights reached 7h30. Earlier lights-out beats any supplement."))
    if cands: focus = min(cands, key=lambda c: c[0])[1]
    import habits
    hab = {"weekly": habits.weekly(start.isoformat(), end.isoformat()), "grid": habits.daily(12), "names": habits.HABITS}
    return {"habits": hab, "start": start.isoformat(), "end": end.isoformat(), "days": [{"date": d["date"], "status": d["status"], "day_type": d["day_type"],
             "totals": d.get("totals"), "eval": d.get("eval"), "weight": d.get("weight"), "steps": d.get("steps"),
             "sleep": (d.get("recovery") or {}).get("sleep"), "exercise": [e["type"] for e in d.get("exercise") or []]} for d in days],
            "status": status, "hits": hits, "averages": avgs, "weight": weight,
            "training": {"sessions": sessions, "session_kcal": kcal, "run_km": round(run_km, 1), "prs": prs},
            "recovery": recovery, "bp": bp, "best": best, "worst": worst, "focus": focus,
            "targets": (days[-1] if days else S[-1]).get("targets")}

def markdown(w):
    f = lambda v, u="": "–" if v is None else f"{v:,}{u}"
    L = [f"# Week of {w['start']} to {w['end']}", "",
         f"Logged: {w['status']['complete']} complete, {w['status']['partial']} partial, {w['status']['unlogged']} unlogged.", "",
         "| Target | Hit | Average |", "|---|---|---|"]
    for k, label in METRICS:
        h = w["hits"][k]; L.append(f"| {label} | {str(h['hit']) + '/' + str(h['of']) if h['of'] else 'no target that week'} | {f(w['averages'][k])} |")
    t, r = w["training"], w["recovery"]
    L += ["", f"**Training:** {', '.join(f'{v} {k}' for k, v in t['sessions'].items()) or 'none'}; {f(t['run_km'])} km run; ~{f(t['session_kcal'])} kcal burnt in sessions and walking.",
          "**New bests:** " + (", ".join(f"{p['lift'].replace('-', ' ')} {p['kg']} kg" + (f" × {p['reps']}" if p.get("reps") else "") for p in t["prs"]) or "none"),
          f"**Recovery:** sleep {f(r['sleep_avg_h'])} h average ({r['nights_ok']}/{r['nights']} nights ≥ 7h30); HRV {f(r['hrv_avg'])} ms; resting HR {f(r['rhr_avg'])}; steps {f(r['steps_avg'])}.",
          f"**Weight:** {f(w['weight']['avg'], ' kg')} average (previous week {f(w['weight']['prev_avg'], ' kg')}).", ""]
    if w["focus"]: L += [f"**Focus for next week:** {w['focus']}", ""]
    return "\n".join(L)

def save(start=None):
    import pathlib
    w = week(start)
    iso = dt.date.fromisoformat(w["start"]).isocalendar()
    p = data.ROOT / "reviews" / f"{iso[0]}-W{iso[1]:02d}.md"
    p.parent.mkdir(exist_ok=True); p.write_text(markdown(w))
    return p
