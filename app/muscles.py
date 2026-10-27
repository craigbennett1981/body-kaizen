"""Muscle map: hard sets per muscle region over a window of days, or for one session, with the lifts behind
each number. Regions match the body diagram in static/vendor/bodymap.js.

Lifts are tagged in the data folder's exercises.yaml (`muscles:` primary, `secondary:` counted as half a set).
Fine tags (front-delts, upper-back...) map to one region; broad tags (shoulders, back, core...) spread to every
region they cover, so older catalogues still draw."""
import datetime as dt
import data
from workouts import _sets, _nice

REGIONS = ["chest", "front-delts", "rear-delts", "biceps", "triceps", "forearms", "abs", "obliques", "traps",
           "upper-back", "lower-back", "glutes", "quads", "hamstrings", "adductors", "calves"]
LABELS = {"front-delts": "Front delts", "rear-delts": "Rear delts", "upper-back": "Upper back and lats",
          "lower-back": "Lower back"}
BROAD = {"shoulders": ["front-delts", "rear-delts"], "delts": ["front-delts", "rear-delts"], "side-delts": ["front-delts", "rear-delts"],
         "back": ["upper-back", "traps"], "lats": ["upper-back"], "rhomboids": ["upper-back"],
         "core": ["abs", "obliques", "lower-back"], "grip": ["forearms"], "legs": ["quads", "hamstrings"],
         "pecs": ["chest"], "abductors": ["glutes"], "hip-abductors": ["glutes"], "hip-adductors": ["adductors"], "quadriceps": ["quads"], "hamstring": ["hamstrings"], "glute": ["glutes"], "calf": ["calves"]}

# Cardio sessions count as set-equivalents: every 10 minutes is one set for the main muscles and half a set for the
# supporting ones. Override or extend in exercises.yaml under `activities:` with the same shape.
ACTIVITIES = {
    "run":   {"muscles": ["quads", "hamstrings", "glutes", "calves"], "secondary": ["abs", "obliques", "adductors"]},
    "walk":  {"muscles": [], "secondary": ["calves", "glutes"]},
    "ruck":  {"muscles": ["quads", "glutes", "calves"], "secondary": ["hamstrings", "traps", "lower-back", "abs"]},
    "swim":  {"muscles": ["upper-back", "front-delts", "rear-delts"], "secondary": ["triceps", "chest", "abs", "quads"]},
    "yoga":  {"muscles": [], "secondary": ["abs", "obliques", "hamstrings", "glutes", "lower-back", "front-delts"]},
    "cycle": {"muscles": ["quads", "glutes"], "secondary": ["hamstrings", "calves"]},
}
MIN_PER_SET = 10

def _minutes(e):
    if e.get("duration_min"): return float(e["duration_min"])
    t = str(e.get("moving_time") or e.get("time") or "")
    try:
        parts = [int(x) for x in t.split(":")]
        return parts[0] * 60 + parts[1] + parts[2] / 60 if len(parts) == 3 else parts[0] + parts[1] / 60
    except Exception: return 0.0

def regions_for(tag):
    t = str(tag).strip().lower().replace(" ", "-").replace("_", "-")
    return [t] if t in REGIONS else BROAD.get(t, [])

def _catalogue():
    p = data.ROOT / "exercises.yaml"
    lifts = (data._load(p).get("lifts") if p.exists() else None) or {}
    alias = {}
    for k, v in lifts.items():
        alias[k] = k
        for a in (v or {}).get("aliases") or []: alias[str(a).lower()] = k
    return lifts, alias

def build(days=7, end=None, date=None, idx=None):
    lifts, alias = _catalogue()
    p_ex = data.ROOT / "exercises.yaml"
    acts = {**ACTIVITIES, **((data._load(p_ex).get("activities") if p_ex.exists() else None) or {})}
    if date:
        p = data.ROOT / "days" / date[:4] / f"{date}.yaml"
        d = data._jsonable(data._load(p)) if p.exists() else {}
        ex = d.get("exercise") or []
        i = int(idx or 0)
        picked = [(date, ex[i])] if 0 <= i < len(ex) else []
        start = stop = date
    else:
        stop = end or data.bkenv.today().isoformat()
        start = (dt.date.fromisoformat(stop) - dt.timedelta(days=int(days) - 1)).isoformat()
        picked = []
        for p in data.day_files():
            ds = p.stem
            if start <= ds <= stop:
                for e in data._jsonable(data._load(p)).get("exercise") or []: picked.append((ds, e))
    out = {r: {"sets": 0.0, "label": LABELS.get(r, r.replace("-", " ").capitalize()), "lifts": []} for r in REGIONS}
    untagged = set()
    for ds, e in picked:
        spec = acts.get(e.get("type")) if not e.get("lifts") else None
        mins = _minutes(e) if spec else 0
        if spec and mins >= 5:
            n = round(mins / MIN_PER_SET, 1)
            name = f"{str(e.get('type')).capitalize()}" + (f" {e['distance_km']} km" if e.get("distance_km") else "")
            seen = set()
            for role, tags, w in (("primary", spec.get("muscles") or [], 1.0), ("secondary", spec.get("secondary") or [], 0.5)):
                for r in {r for t in tags for r in regions_for(t)} - seen:
                    seen.add(r); out[r]["sets"] += n * w
                    out[r]["lifts"].append({"name": name, "date": ds, "sets": n, "role": role, "minutes": round(mins)})
            continue
        for l in e.get("lifts") or []:
            key = alias.get(str(l.get("ex", "")).lower(), l.get("ex"))
            spec = lifts.get(key) or {}
            n = sum(1 for s in _sets(l.get("sets")) if not s["warmup"])
            if not n: continue
            prim, sec = spec.get("muscles") or [], spec.get("secondary") or []
            if not prim and not sec: untagged.add(_nice(key)); continue
            seen = set()
            for role, tags, w in (("primary", prim, 1.0), ("secondary", sec, 0.5)):
                for r in {r for t in tags for r in regions_for(t)} - seen:
                    seen.add(r)
                    out[r]["sets"] += n * w
                    out[r]["lifts"].append({"name": _nice(key), "date": ds, "sets": n, "role": role})
    for r in out.values():
        r["sets"] = round(r["sets"], 1)
        merged = {}
        for x in r["lifts"]:
            m = merged.setdefault((x["name"], x["role"], x.get("minutes") is not None), {"name": x["name"], "role": x["role"], "sets": 0, "dates": []})
            m["sets"] = round(m["sets"] + x["sets"], 1); m["dates"].append(x["date"])
            if x.get("minutes") is not None: m["minutes"] = m.get("minutes", 0) + x["minutes"]
        r["lifts"] = sorted(merged.values(), key=lambda x: (x["role"] != "primary", -x["sets"], x["name"]))
    return {"start": start, "end": stop, "session": bool(date), "regions": out,
            "untrained": [k for k, v in out.items() if not v["sets"]], "untagged": sorted(untagged)}
