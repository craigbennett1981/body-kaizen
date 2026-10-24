#!/usr/bin/env python3
"""Import a Hevy CSV export (Settings > Export & Import Data > Export Workouts) into the day files.
Hevy is the source of truth for sets: each workout's lifts replace the lifts on that day's gym entry;
Garmin fields (HR, kcal, zones) on the same entry are kept. Warm-up sets are kept and marked.
usage: hevy_import.py path/to/workout_data.csv [--dry-run]"""
import csv, datetime as dt, pathlib, sys, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bkenv  # noqa: E402
ROOT = bkenv.DATA

HEVY = {   # Hevy exercise title -> lift id in exercises.yaml
    "Squat (Smith Machine)": "smith-squat", "Romanian Deadlift (Smith Machine)": "smith-rdl",
    "Romanian Deadlift (Barbell)": "barbell-rdl", "Cable Fly Crossovers": "cable-fly", "Triceps Pushdown": "triceps-pushdown",
    "Bicep Curl (Cable)": "biceps-curl", "Cable Crunch": "cable-crunch", "Seated Cable Row - Bar Grip": "seated-row",
    "Lat Pulldown (Cable)": "lat-pulldown", "Shoulder Press (Machine Plates)": "shoulder-press", "Seated Leg Curl (Machine)": "leg-curl",
    "Leg Extension (Machine)": "leg-extension", "Pullover (Dumbbell)": "db-pullover", "Bench Press (Barbell)": "bench-press",
    "Incline Bench Press (Dumbbell)": "incline-db-bench", "Plank": "plank", "Standing Calf Raise": "calf-raise", "Farmers Walk": "farmers-walk",
}

def num(s):
    if s in (None, ""): return None
    v = float(s); return int(v) if v == int(v) else round(v, 1)

def set_str(r):
    kg, reps, sec = num(r["weight_kg"]), num(r["reps"]), num(r["duration_seconds"])
    km = float(r["distance_km"]) if r["distance_km"] not in (None, "") else None   # not rounded: 0.06 km = 60 m
    if km: return f"{kg}kg@{int(round(km * 1000))}m"
    if sec and not reps: return f"{int(sec)}s"
    if reps is not None and kg is not None: return f"{kg}x{int(reps)}"
    if reps is not None: return f"0x{int(reps)}"
    return None

def load(path):
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    ws = {}
    for r in rows:
        st = dt.datetime.strptime(r["start_time"], "%d %b %Y, %H:%M")
        w = ws.setdefault(r["start_time"], {"start": st, "end": r["end_time"], "title": r["title"], "description": r["description"], "lifts": {}, "unknown": set()})
        lid = HEVY.get(r["exercise_title"])
        if not lid: w["unknown"].add(r["exercise_title"]); continue
        s = set_str(r)
        if not s: continue
        if r["set_type"] == "warmup": s = "w" + s
        w["lifts"].setdefault(lid, []).append(s)
    return sorted(ws.values(), key=lambda w: w["start"])

def apply(w, dry):
    d = w["start"].date(); p = ROOT / "days" / str(d.year) / f"{d.isoformat()}.yaml"
    day = yaml.safe_load(p.read_text()) if p.exists() else {"date": d, "status": "unlogged", "day_type": "training", "meals": {}}
    ex = day.setdefault("exercise", []) or []
    day["exercise"] = ex
    gyms = [e for e in ex if e.get("type") == "gym"]
    t = w["start"].strftime("%H:%M")
    def mins(e):
        try: return abs((dt.datetime.strptime(str(e.get("start")), "%H:%M") - dt.datetime.strptime(t, "%H:%M")).total_seconds())
        except Exception: return 1e9
    e = min(gyms, key=mins) if gyms else None
    action = "updated"
    if e is None:
        e = {"type": "gym"}; ex.append(e); action = "added"
    old = e.get("lifts")
    e.setdefault("start", t)
    e["hevy_name"] = w["title"]
    try: e.setdefault("duration_min", int((dt.datetime.strptime(w["end"], "%d %b %Y, %H:%M") - w["start"]).total_seconds() // 60))
    except Exception: pass
    e["lifts"] = [{"ex": k, "sets": v} for k, v in w["lifts"].items()]
    if e.get("source") in (None, "notepad"): e["source"] = "hevy"
    if day.get("day_type") == "rest": day["day_type"] = "training"
    changed = old != e["lifts"]
    if not dry and (changed or action == "added"):
        p.write_text(yaml.safe_dump(day, sort_keys=False, allow_unicode=True, default_flow_style=None, width=140))
    return p, action if changed or action == "added" else "same", old

def main():
    path = sys.argv[1]; dry = "--dry-run" in sys.argv
    ws = load(path); touched = []
    for w in ws:
        p, act, old = apply(w, dry)
        n = sum(len(v) for v in w["lifts"].values())
        print(f"{w['start']:%Y-%m-%d %H:%M}  {w['title']:<18} {len(w['lifts']):>2} lifts {n:>3} sets  {act}{'  (had ' + str(len(old)) + ' lifts)' if old and act == 'updated' else ''}{'  unknown: ' + ', '.join(sorted(w['unknown'])) if w['unknown'] else ''}")
        if act != "same": touched.append(p)
    if not dry:
        import compute
        for p in touched: compute.process(p)
    print(f"{len(ws)} workouts, {len(touched)} day files {'would change' if dry else 'changed'}")

if __name__ == "__main__":
    main()
