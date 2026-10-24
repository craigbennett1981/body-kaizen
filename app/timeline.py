"""One chronological list of what happened: labs, scans, target changes, episodes, training changes, events.yaml."""
import data, longevity

def _s(d): return str(d)[:10]

def events():
    out = []
    add = lambda d, kind, what, detail=None: out.append({"date": _s(d), "kind": kind, "what": what, **({"detail": detail} if detail else {})})
    for dr in longevity._yaml("labs.yaml"):
        names = {m: v.get("name", m) for m, v in longevity.cfg()["markers"].items()}
        add(dr["date"], "lab", f"Blood test ({dr.get('lab', 'lab')})", ", ".join(names.get(r["marker"], r["marker"]) for r in dr.get("results") or []))
    for b in longevity._yaml("inbody.yaml"):
        add(b["date"], "scan", "InBody scan", f"{b.get('weight_kg')} kg, {b.get('pbf_pct')}% fat, muscle {b.get('smm_kg')} kg")
    for e in longevity._yaml("episodes.yaml"):
        add(e["start"], "episode", "Off episode", e.get("what")); out[-1]["end"] = _s(e.get("end") or e["start"])
    T = data._load(data.ROOT / "targets.yaml")
    for era in T.get("intake") or []:
        add(era["from"], "target", f"Food targets: {era.get('label', 'changed')}")
    for w in T.get("weight") or []:
        add(w["from"], "target", f"Weight target {w['kg']} kg", w.get("source"))
    plan = (data._load(data.ROOT / "exercises.yaml").get("training_plan") or {})
    if plan.get("block_start"):
        add(plan["block_start"], "training", "Training block started", f"{plan.get('rep_range', [8, 12])[0]}–{plan.get('rep_range', [8, 12])[1]} reps, deload every {plan.get('deload_every_weeks', 4)} weeks")
    p = data.ROOT / "events.yaml"
    for e in (data._load(p) if p.exists() else []) or []:
        add(e["date"], e.get("kind", "life"), e["what"], e.get("detail"))
    return sorted(out, key=lambda e: e["date"], reverse=True)
