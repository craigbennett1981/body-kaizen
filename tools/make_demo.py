#!/usr/bin/env python3
"""Generate the demo data folder: ~90 days of made-up but realistic data for a fictional person ("Sam",
42) so every dashboard tab has something to show. Nothing here comes from a real person.

usage: python tools/make_demo.py [OUT_DIR] [--end YYYY-MM-DD] [--days N] [--seed N]
       (defaults: demo/, end 2026-10-23, 90 days, seed 7)

Writes day files, Garmin-style raw imports (daily summaries, sleep stages, intraday steps and body
battery, workout heart-rate traces), measurements and the reference files from demo-template/, then
runs scripts/compute.py so every day has its totals. Same seed, same data.
"""
import argparse, datetime as dt, json, math, os, pathlib, random, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
CODE = HERE.parent
TZ_NAME, UTC_OFFSET_H = "UTC", 0   # the demo person lives on UTC; local times below are converted with this offset

ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default=str(CODE / "demo"))
ap.add_argument("--end", default="2026-10-23")
ap.add_argument("--days", type=int, default=90)
ap.add_argument("--seed", type=int, default=7)
A = ap.parse_args()
R = random.Random(A.seed)
OUT = pathlib.Path(A.out).resolve()
END = dt.date.fromisoformat(A.end)
START = END - dt.timedelta(days=A.days - 1)
DAYS = [START + dt.timedelta(days=i) for i in range(A.days)]

def j(x, s): return round(x + R.gauss(0, s), 1)
def lerp(a, b, f): return a + (b - a) * f
def hm(m): m = int(m) % 1440; return f"{m // 60:02d}:{m % 60:02d}"
def frac(d): return (d - START).days / max(1, A.days - 1)
def gmt(d, minute):   # local minute-of-day on date d -> naive GMT datetime
    return dt.datetime.combine(d, dt.time()) + dt.timedelta(minutes=minute) - dt.timedelta(hours=UTC_OFFSET_H)
def ms(t): return int(t.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)

def yaml_dump(obj):
    import yaml
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, default_flow_style=None, width=200)

# ---------------------------------------------------------------- weekly plan
# Mon gym A, Tue easy run, Wed gym B, Thu rest, Fri gym A, Sat long run (or swim), Sun rest
PLAN = {0: "gymA", 1: "run", 2: "gymB", 3: "rest", 4: "gymA", 5: "long", 6: "rest"}
GYM_A = ["smith-squat", "seated-row", "shoulder-press", "leg-curl", "cable-fly", "biceps-curl", "farmers-walk"]
GYM_B = ["smith-rdl", "lat-pulldown", "chin-up", "leg-extension", "triceps-pushdown", "cable-crunch", "farmers-walk"]
START_KG = {"smith-squat": 50, "seated-row": 31.8, "shoulder-press": 27.2, "leg-curl": 59, "cable-fly": 36.3,
            "biceps-curl": 34, "smith-rdl": 50, "lat-pulldown": 36.3, "leg-extension": 45.4, "triceps-pushdown": 40.8,
            "cable-crunch": 54.5}
INC = {"smith-squat": 2.5, "smith-rdl": 2.5}
lift_state = {k: {"kg": v, "reps": 8} for k, v in START_KG.items()}
chin = [4, 3, 3]; farm = {"kg": 40, "m": 40}

def gym_session(kind, d, late):
    lifts = []
    for ex in (GYM_A if kind == "gymA" else GYM_B):
        if ex == "farmers-walk":
            lifts.append({"ex": ex, "sets": [f"{farm['kg']}kg@{farm['m']}m"] * 3})
            if R.random() < 0.4: farm["m"] += 20
            if farm["m"] > 80: farm["m"] = 40; farm["kg"] = min(60, farm["kg"] + 5)
            continue
        if ex == "chin-up":
            lifts.append({"ex": ex, "sets": [f"0x{r}" for r in chin]})
            i = R.randrange(3); chin[i] = min(12, chin[i] + 1)
            continue
        st = lift_state[ex]
        reps = [st["reps"], st["reps"], max(8, st["reps"] - R.choice([0, 0, 1]))] if not late else [st["reps"], max(8, st["reps"] - 1), 8]
        lifts.append({"ex": ex, "sets": [f"{st['kg']}x{r}" for r in reps]})
        if min(reps) >= 12:
            st["kg"] = round(st["kg"] + INC.get(ex, 4.5), 1); st["reps"] = 8
        elif R.random() < 0.75:
            st["reps"] = min(12, st["reps"] + 1)
    return lifts

# ---------------------------------------------------------------- food
BREAKFASTS = [
    ["{oats}g oats", "2 eggs", "English breakfast tea and low fat milk", "{blue}g blueberries", "1 banana"],
    ["{sour}g sourdough", "2 eggs", "English breakfast tea and low fat milk"],
    ["{yog}g yogurt + {chia}g soaked chia seeds", "English breakfast tea and low fat milk", "1 banana"],
]
LUNCHES = [
    ["{rice}g rice", "{chick}g chicken breast", "{veg}g broccoli"],
    ["{pasta}g pasta", "{chick}g chicken breast", "{toms}g tomato pepper sauce"],
    ["{rice}g rice", "{fish}g salmon", "{veg}g spinach"],
    ["{rice}g rice", "{tofu}g tofu", "{veg}g cabbage", "{pork}g pork loin"],
    ["salad {salad}g", "{chick}g chicken breast", "{bread}g sourdough", "{avo}g avocado"],
]
DINNERS = [
    ["{rice}g rice", "{pork}g pork loin", "{veg}g broccoli"],
    ["{potato}g potato", "{beef}g lean beef", "{veg}g green bean"],
    ["{rice}g rice", "{fish}g fish", "{veg}g bok choy"],
    ["{pasta}g pasta", "{beef}g bolognese beef"],
    ["{rice}g rice", "{chick}g chicken breast", "{veg}g spinach", "200ml miso soup"],
]
SNACKS = ["{gran}g granola + 150ml low fat milk", "{nuts}g almonds and cashews", "{fruit}g apple", "{fruit}g pear", "{fruit}g guava", "{dates}g dates", "300ml low fat milk + 1 scoop protein powder",
          "{yog}g yogurt + half scoop protein powder", "1 kiwi"]
TREATS = [["2 slices pepperoni pizza"], ["ice cream 180 cal"], ["1 croissant"], ["brownie 250 cal"], ["cheesecake 300 cal"]]

def fill(t):
    v = dict(oats=R.choice([45, 50, 52, 55]), blue=R.randint(60, 100), sour=R.choice([50, 56, 60]), yog=R.randint(140, 180),
             chia=R.randint(70, 110), rice=R.randint(140, 200), chick=R.randint(130, 180), veg=R.randint(80, 140),
             pasta=R.randint(170, 230), toms=R.randint(50, 80), fish=R.randint(110, 150), tofu=R.randint(80, 120),
             pork=R.randint(90, 130), salad=R.randint(120, 180), bread=R.randint(40, 60), potato=R.randint(180, 250),
             beef=R.randint(120, 160), fruit=R.randint(120, 200), dates=R.randint(30, 60), gran=R.randint(40, 55), nuts=R.randint(20, 30), avo=R.randint(50, 80))
    return t.format(**v)

HERO = {   # the last day is fixed, so the README screenshots show a typical good training day
    "breakfast": [("52g oats", "07:20"), ("2 eggs", "07:20"), ("English breakfast tea and low fat milk", "07:20"), ("80g blueberries", "07:20")],
    "lunch": [("170g rice", "12:40"), ("165g chicken breast", "12:40"), ("120g broccoli", "12:40")],
    "dinner": [("130g rice", "19:45"), ("140g salmon", "19:45"), ("120g spinach", "19:45")],
    "snacks": [("155g yogurt + 90g soaked chia seeds", "10:45"), ("170g pear", "15:30"), ("300ml low fat milk + 1 scoop protein powder", "19:00"),
               ("150g guava", "21:00")],
}

sys.path.insert(0, str(CODE / "scripts"))
os.environ["FT_DATA"] = str(OUT)   # the matcher reads overrides/settings from the demo folder
import nutrition as N   # the real food matcher, so the demo is scored exactly as the dashboard will score it
BAND = {"rest": (1900, 2000), "training": (2100, 2200), "big": (2250, 2350)}   # matches demo-template/targets.yaml

def score(m, d, dtype):
    t = dict.fromkeys(("k", "p", "sf", "fib"), 0.0)
    for items in m.values():
        for it in items:
            for c in N.resolve(it["raw"], d.isoformat())[0]:
                mm = N.macros(c)
                for k in t: t[k] += mm[k]
    lo, hi = BAND[dtype]
    return (max(0, lo - t["k"]) + max(0, t["k"] - hi)) / 25 + max(0, 150 - t["p"]) / 5 + max(0, t["sf"] - 20) * 2 + max(0, 30 - t["fib"])

def meals_for(d, kind, last_day, dtype="rest"):
    """Most days aim for the targets (best of several draws); about a third are left as they come, misses and all."""
    if last_day: return {k: [{"raw": r, "time": t} for r, t in v] for k, v in HERO.items()}
    if R.random() < 0.32: return draw_meals(d, kind)
    return min((draw_meals(d, kind) for _ in range(120)), key=lambda m: score(m, d, dtype))

def draw_meals(d, kind):
    m = {"breakfast": [], "lunch": [], "dinner": [], "snacks": []}
    bt = 7 * 60 + R.randint(0, 60); lt = 12 * 60 + R.randint(0, 75); dtm = 18 * 60 + 30 + R.randint(0, 75)
    for x in R.choice(BREAKFASTS): m["breakfast"].append({"raw": fill(x), "time": hm(bt)})
    for x in R.choice(LUNCHES): m["lunch"].append({"raw": fill(x), "time": hm(lt)})
    for x in R.choice(DINNERS): m["dinner"].append({"raw": fill(x), "time": hm(dtm)})
    for i in range(R.choice([2, 2, 3, 3])):
        st = R.choice([10 * 60 + 30, 15 * 60 + 30, 16 * 60 + 45, 21 * 60]) + R.randint(0, 30)
        m["snacks"].append({"raw": fill(R.choice(SNACKS)), "time": hm(st)})
    if kind != "rest" or R.random() < 0.3:   # post-training shake
        m["snacks"].append({"raw": "300ml low fat milk + 1 scoop protein powder", "time": hm(lt + 240)})
    if (d.weekday() in (5, 6) and R.random() < 0.45) or R.random() < 0.06:
        for x in R.choice(TREATS): m["snacks"].append({"raw": x, "time": hm(20 * 60 + R.randint(0, 60))})
    m["snacks"].sort(key=lambda x: x["time"])
    return m

# ---------------------------------------------------------------- per-day generation
def sleep_levels(d, bed, wake):
    """Garmin-style sleep stages for the night ending on the morning of d (bed = minutes before midnight)."""
    out, t = [], -bed
    cycle = 0
    while t < wake:
        seq = [(1, 20), (0, max(10, 45 - cycle * 10)), (1, 25), (2, 15 + cycle * 7)]
        for lvl, mins in seq:
            mins = max(5, int(mins + R.gauss(0, 4)))
            e = min(wake, t + mins)
            if e <= t: break
            out.append({"startGMT": gmt(d, t).isoformat() + ".0", "endGMT": gmt(d, e).isoformat() + ".0", "activityLevel": float(lvl)})
            t = e
            if R.random() < 0.07 and t < wake - 10:
                out.append({"startGMT": gmt(d, t).isoformat() + ".0", "endGMT": gmt(d, t + 3).isoformat() + ".0", "activityLevel": 3.0}); t += 3
        cycle += 1
    st = {"deep": 0, "light": 0, "rem": 0, "awake": 0}
    for x in out:
        k = {0: "deep", 1: "light", 2: "rem", 3: "awake"}[int(x["activityLevel"])]
        a = dt.datetime.fromisoformat(x["startGMT"][:19]); b = dt.datetime.fromisoformat(x["endGMT"][:19])
        st[k] += int((b - a).total_seconds() // 60)
    return out, st

def hr_trace(kind, start_ms, minutes, hr_avg_target):
    s, t, pts = [], 0, []
    if kind == "gym":
        hr = 92
        while t < minutes * 60:
            work = R.randint(35, 55); rest = R.randint(80, 130)
            peak = R.randint(122, 142)
            for k in range(0, work, 5):
                hr = hr + (peak - hr) * 0.35; pts.append((t + k, hr + R.gauss(0, 1.5)))
            t += work
            for k in range(0, rest, 5):
                hr = hr + (98 + R.gauss(0, 3) - hr) * 0.12; pts.append((t + k, hr + R.gauss(0, 1.5)))
            t += rest
    else:
        for k in range(0, minutes * 60, 5):
            m = k / 60
            base = 105 + min(1, m / 6) * (hr_avg_target - 105) + m * 0.25
            pts.append((k, base + R.gauss(0, 1.5)))
    return [[start_ms + int(x * 1000), int(round(h)), None] for x, h in pts]

def set_top(sets):
    """(heaviest kg, total reps at that kg) from ['57.5x12', ...]; None for carries and bodyweight."""
    xs = [tuple(map(float, str(x).split("x"))) for x in sets if "x" in str(x) and "@" not in str(x)]
    xs = [(k, r) for k, r in xs if k > 0]
    if not xs: return None
    kg = max(k for k, _ in xs); return (kg, int(sum(r for k, r in xs if k == kg)))

def prev_session(path, name):
    import yaml
    for q in sorted(path.parent.parent.rglob("*.yaml"), reverse=True):
        if q.stem >= path.stem: continue
        for e in (yaml.safe_load(q.read_text()).get("exercise") or []):
            if e.get("type") == "gym" and e.get("name") == name: return {l["ex"]: l["sets"] for l in e.get("lifts", [])}
    return None

def write_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj))

def main():
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "days").mkdir(parents=True)
    for f in (HERE.parent / "demo-template").glob("*.yaml"): shutil.copy(f, OUT / f.name)
    # the demo person's profile, so the dashboard doesn't ask for one (foods come from foods/starter.yaml)
    st = OUT / "settings.yaml"
    st.write_text(yaml_dump({"profile": {"name": "Sam (demo)", "start_date": START.isoformat()}, "timezone": TZ_NAME}) + "\n" + st.read_text())
    (OUT / "overrides.yaml").write_text("# Fixes for log lines the food matcher gets wrong:  \"raw text\": [{item: id, g: 100}]\n{}\n")
    vo2, fitage = {}, {}
    aid = 30000000000
    weights, tests, bp_all = [], [], []
    hrv7 = []
    for i, d in enumerate(DAYS):
        f = frac(d); ds = d.isoformat()
        kind = PLAN[d.weekday()]
        if kind == "long" and (d.isocalendar()[1] % 3 == 0): kind = "swim"
        travel = dt.date(2026, 9, 14) <= d <= dt.date(2026, 9, 16)
        if travel: kind = "rest"
        sick = dt.date(2026, 9, 2) <= d <= dt.date(2026, 9, 4)
        if sick: kind = "rest"
        unlogged = travel and d.day == 15
        day = {"date": ds, "status": "complete" if d != END else "complete"}
        # weight: 82.4 -> 78.6 with water noise; weekend bump
        kg = lerp(82.4, 78.6, f) + R.gauss(0, 0.25) + (0.35 if d.weekday() in (6, 0) else 0)
        bf = lerp(22.8, 19.6, f) + R.gauss(0, 0.3)
        if R.random() < 0.85 and not travel:
            day["weight"] = {"kg": round(kg, 1), "fasted": True, "time": hm(6 * 60 + 45 + R.randint(0, 40)), "bf_pct": round(bf, 1),
                             "muscle_kg": round(kg * (1 - bf / 100) * 0.95, 1), "visceral": 8 if f < .5 else 7, "water_pct": round(57 + R.gauss(0, .5), 1),
                             "bmi": round(kg / 1.78 ** 2, 1), "source": "scale-app"}
            weights.append((ds, kg))
        # recovery
        bed = R.randint(30, 95) if d.weekday() not in (5, 6) else R.randint(60, 140)   # minutes before midnight
        wake = 6 * 60 + 30 + R.randint(-20, 40) + (45 if d.weekday() in (5, 6) else 0)
        if sick: bed += 30
        levels, st = sleep_levels(d, bed, wake)
        slept = st["deep"] + st["light"] + st["rem"]
        hrv = int(lerp(56, 66, f) + R.gauss(0, 5) - (12 if sick else 0) - (6 if d.weekday() == 6 and R.random() < .5 else 0))
        hrv7.append(hrv); h7 = int(sum(hrv7[-7:]) / len(hrv7[-7:]))
        rhr = int(round(lerp(56, 51, f) + R.gauss(0, 1.2) + (4 if sick else 0)))
        bb = max(20, min(100, int(lerp(55, 72, f) + (slept - 420) / 6 + R.gauss(0, 6) - (20 if sick else 0))))
        score = max(45, min(95, int(70 + (slept - 420) / 4 + R.gauss(0, 5))))
        day["recovery"] = {"sleep": f"{slept // 60}h{slept % 60:02d}m", "sleep_stages_min": {k: st[k] for k in ("deep", "light", "rem")},
                           "awake_min": st["awake"], "in_bed": f"{hm(-bed)}–{hm(wake)}", "sleep_start": (dt.datetime.combine(d, dt.time()) - dt.timedelta(minutes=bed)).isoformat()[:16],
                           "sleep_end": (dt.datetime.combine(d, dt.time()) + dt.timedelta(minutes=wake)).isoformat()[:16], "sleep_score": score,
                           "overnight_hr": rhr + 4, "hrv_ms": hrv, "hrv_7d_ms": h7, "hrv_status": "balanced" if hrv > h7 - 8 else "unbalanced",
                           "rhr": rhr, "body_battery": bb, "stress_avg": int(28 + R.gauss(0, 5) + (12 if sick else 0)), "source": "garmin"}
        if R.random() < 0.6:
            day["feel"] = {"overall": 2 if sick else R.choice([3, 4, 4, 4, 5]), "energy": 2 if sick else R.choice([3, 4, 4, 5]), "mood": R.choice([3, 4, 4, 5]),
                           "gut": R.choice([3, 4, 4]), "stress": R.choice([2, 2, 3])}
        if sick: day["symptoms"] = [{"what": "sore throat", "severity": 2}, {"what": "fatigue", "severity": 2}]
        # blood pressure most mornings, trending down
        if R.random() < 0.55:
            s = int(lerp(126, 118, f) + R.gauss(0, 4)); di = int(lerp(81, 76, f) + R.gauss(0, 3))
            day["vitals"] = {"bp": [{"time": hm(7 * 60 + 30 + R.randint(0, 40)), "sys": s, "dia": di, "pulse": rhr + R.randint(6, 14), "source": "bp-app"}]}
            bp_all.append(s)
        steps = int(max(2500, R.gauss(9500, 2500) + (2000 if kind in ("run", "long") else 0) - (5000 if sick else 0)))
        day["steps"] = steps
        # training
        ex = []
        if kind.startswith("gym"):
            start = 17 * 60 + 30 + R.randint(-60, 90); dur = R.randint(52, 68)
            late = R.random() < 0.15
            hravg = int(112 + R.gauss(0, 4)); kcal = int(300 + R.gauss(0, 30))
            aid += 1
            e = {"type": "gym", "garmin_id": aid, "source": "garmin", "start": hm(start), "duration_min": dur, "hr": {"avg": hravg, "max": hravg + R.randint(20, 32)},
                 "kcal": {"total": kcal, "active": int(kcal * .78)}, "zones_min": {"z1": R.randint(12, 20), "z2": R.randint(26, 36), "z3": R.randint(3, 10)},
                 "garmin_name": "Strength", "name": "Lower + pull" if kind == "gymA" else "Hinge + push", "lifts": gym_session(kind, d, late)}
            ex.append(e)
            write_json(OUT / "imports/garmin/activities" / f"{aid}.json", {"activity_id": aid, "type": "strength_training", "start_local": f"{ds} {hm(start)}:00",
                       "start_gmt": gmt(d, start).isoformat(sep=" "), "duration_s": dur * 60, "samples": hr_trace("gym", ms(gmt(d, start)), dur, hravg),
                       "aerobic_te": round(R.uniform(1.8, 2.6), 1), "anaerobic_te": round(R.uniform(0.4, 1.2), 1), "te_label": "AEROBIC_BASE",
                       "body_battery_change": -R.randint(5, 10), "summary": {"averageHR": hravg, "maxHR": hravg + 25, "recoveryHeartRate": R.randint(30, 42)}})
        elif kind in ("run", "long"):
            km = round(R.uniform(5, 6.5) if kind == "run" else lerp(7, 11, f) + R.uniform(-0.5, 0.5), 2)
            pace = lerp(7.1, 6.45, f) + R.gauss(0, 0.12) + (0.25 if kind == "long" else 0)   # min/km
            secs = int(km * pace * 60); start = (6 * 60 + 40 + R.randint(0, 40)) if kind == "long" else (18 * 60 + R.randint(0, 60))
            hravg = int(lerp(146, 139, f) + R.gauss(0, 2.5) + (3 if kind == "long" else 0))
            aid += 1
            e = {"type": "run", "garmin_id": aid, "source": "garmin", "mode": "outdoor", "effort": "long" if kind == "long" else "easy", "start": hm(start),
                 "duration_min": secs // 60, "distance_km": km, "time": f"{secs // 60}:{secs % 60:02d}", "distance_source": "gps",
                 "hr": {"avg": hravg, "max": hravg + R.randint(10, 18)}, "kcal": {"total": int(km * 75), "active": int(km * 64)}, "cadence": R.randint(158, 166),
                 "zones_min": {"z1": 2, "z2": int(secs / 60 * .35), "z3": int(secs / 60 * .55), "z4": int(secs / 60 * .1)}, "garmin_name": "Running"}
            ex.append(e)
            write_json(OUT / "imports/garmin/activities" / f"{aid}.json", {"activity_id": aid, "type": "running", "start_local": f"{ds} {hm(start)}:00",
                       "start_gmt": gmt(d, start).isoformat(sep=" "), "duration_s": secs, "samples": hr_trace("run", ms(gmt(d, start)), secs // 60, hravg),
                       "aerobic_te": round(R.uniform(2.6, 3.6), 1), "anaerobic_te": round(R.uniform(0.2, 1.0), 1), "te_label": "TEMPO" if kind == "run" else "AEROBIC_BASE",
                       "body_battery_change": -R.randint(10, 18), "summary": {"averageHR": hravg, "maxHR": hravg + 14, "recoveryHeartRate": R.randint(32, 46)}})
        elif kind == "swim":
            m_ = R.choice([750, 1000, 1200]); aid += 1
            ex.append({"type": "swim", "garmin_id": aid, "source": "garmin", "start": hm(8 * 60), "duration_min": int(m_ / 30), "distance_m": m_, "pool_m": 25,
                       "hr": {"avg": 128, "max": 148}, "kcal": {"total": int(m_ * .32), "active": int(m_ * .27)}, "garmin_name": "Pool Swim"})
        if ex: day["exercise"] = ex
        # meals
        if unlogged:
            day["status"] = "unlogged"; day["meals"] = {"breakfast": [], "lunch": [], "dinner": [], "snacks": []}
        else:
            dtype = "rest" if kind == "rest" else "big" if kind == "long" else "training"
            day["meals"] = meals_for(d, kind, d == END, dtype)
        # energy (Garmin): BMR + steps + workouts
        bmr = int(lerp(1760, 1715, f)); active = int(steps * 0.045 + sum((x.get("kcal") or {}).get("active", 0) for x in ex))
        day["energy"] = {"total": bmr + active, "active": active, "bmr": bmr, "source": "garmin"}
        day["intensity_min"] = {"moderate": sum(x["duration_min"] for x in ex if x["type"] != "run"), "vigorous": sum(x["duration_min"] for x in ex if x["type"] == "run"), "source": "garmin"}
        (OUT / "days" / ds[:4]).mkdir(parents=True, exist_ok=True)
        (OUT / "days" / ds[:4] / f"{ds}.yaml").write_text(yaml_dump(day))
        # raw Garmin day: summary, sleep stages, intraday steps (15 min, GMT ISO) and body battery (epoch ms)
        stp, left = [], steps
        weights15 = [0.0] * 96
        for q in range(96):
            mnt = q * 15
            if mnt < wake or mnt > 23 * 60: continue
            weights15[q] = 1.0 + (3.0 if 7 * 60 + 30 <= mnt <= 9 * 60 or 12 * 60 <= mnt <= 13 * 60 or 18 * 60 <= mnt <= 19 * 60 else 0) + R.random()
        tw = sum(weights15)
        for q in range(96):
            stp.append([gmt(d, q * 15).isoformat() + ".0", int(steps * weights15[q] / tw)])
        bbp, level = [], max(10, bb - 45)
        for q in range(0, 1440, 15):
            if q < wake: level = min(100, level + 45 / max(1, wake / 15))
            else: level = max(8, level - (0.55 if q < 17 * 60 else 0.8) - (2.5 if any(x.get("start") and 0 <= q - (int(x["start"][:2]) * 60 + int(x["start"][3:])) < 60 for x in ex) else 0))
            bbp.append([ms(gmt(d, q)), int(level)])
        write_json(OUT / "imports/garmin" / ds[:4] / f"{ds}.json", {"date": ds, "summary": {
            "totalKilocalories": day["energy"]["total"], "activeKilocalories": active, "bmrKilocalories": bmr, "totalSteps": steps,
            "wellnessEndTimeLocal": (d + dt.timedelta(days=1)).isoformat() + "T00:00:00.0", "bodyBatteryMostRecentValue": bbp[-1][1],
            "lastSyncTimestampGMT": gmt(d, 23 * 60 + 50).isoformat() + ".0"},
            "sleep": {"sleepLevels": levels}, "steps_intraday": stp, "body_battery_intraday": bbp, "stress_intraday": []})
        if d.weekday() == 5:
            vo2[ds] = {"vo2max": round(lerp(44.2, 47.1, f) + R.gauss(0, .3), 1)}
            day["fitness"] = {"vo2max": vo2[ds]["vo2max"], "source": "garmin"}
            (OUT / "days" / ds[:4] / f"{ds}.yaml").write_text(yaml_dump(day))
        if d.weekday() == 0 and f > .5:
            fitage[ds] = {"chronologicalAge": 42, "fitnessAge": round(lerp(41, 37.5, f), 1), "achievableFitnessAge": 35.8,
                          "components": {"bmi": {"value": round(kg / 1.78 ** 2, 1), "targetValue": 23.0}, "rhr": {"value": rhr},
                                         "vigorousDaysAvg": {"value": 1.6, "targetValue": 3}, "vigorousMinutesAvg": {"value": 62, "targetValue": 75}}}
    write_json(OUT / "imports/garmin/vo2max.json", vo2)
    write_json(OUT / "imports/garmin/fitness_age.json", fitage)
    # coach comments on the latest gym session and run
    for p in sorted((OUT / "days").rglob("*.yaml"), reverse=True)[:7]:
        import yaml
        dd = yaml.safe_load(p.read_text())
        for e in dd.get("exercise") or []:
            if e["type"] == "gym" and "coach" not in e:
                prev = prev_session(p, e["name"])
                ups, reps_up = [], []
                for l in e["lifts"]:
                    top = set_top(l["sets"]); old = set_top(prev.get(l["ex"], [])) if prev else None
                    nice = l["ex"].replace("smith-", "").replace("-", " ")
                    if not old or not top: continue
                    if top[0] > old[0]:
                        ups.append(nice); l["note"] = f"Up to {top[0]:g} kg (from {old[0]:g}). Build back to 3 × 12 here before the next step."
                    elif top[0] == old[0] and top[1] > old[1]:
                        reps_up.append(nice); l["note"] = f"{top[1] - old[1]} more rep{'s' if top[1] - old[1] > 1 else ''} than last time at the same weight."
                txt = (f"Heavier on {', '.join(ups)}" if ups else "") + ("; " if ups and reps_up else "") + (f"more reps on {', '.join(reps_up)}" if reps_up else "")
                e["coach"] = [{"kind": "good", "text": (txt[0].upper() + txt[1:] + ". Progress on every main lift.") if txt else "Session done at the planned weights."},
                              {"kind": "info", "text": "About 2.5 minutes between efforts on the heart-rate trace. That's about right for the heavy lifts; keep accessories tighter."}]
            if e["type"] == "run" and "coach" not in e:
                e["coach"] = [{"kind": "good", "text": "Same pace as last month at 4 bpm lower heart rate: the aerobic base is building."}]
        p.write_text(yaml_dump(dd))
    # measurements
    M = OUT / "measurements"; M.mkdir(exist_ok=True)
    (M / "labs.yaml").write_text(yaml_dump([
        {"date": "2026-06-20", "lab": "Demo Lab", "results": [
            {"marker": "total_chol", "value": 5.9, "unit": "mmol/L", "ref_high": 5.2, "flag": "H"}, {"marker": "hdl", "value": 1.21, "unit": "mmol/L", "ref_low": 1.0},
            {"marker": "ldl", "value": 3.95, "unit": "mmol/L", "ref_high": 3.4, "flag": "H"}, {"marker": "tg", "value": 1.62, "unit": "mmol/L", "ref_high": 1.7},
            {"marker": "hba1c", "value": 5.6, "unit": "%", "ref_high": 5.6}, {"marker": "glucose", "value": 5.4, "unit": "mmol/L", "ref_high": 6.0}]},
        {"date": "2026-10-06", "lab": "Demo Lab", "results": [
            {"marker": "total_chol", "value": 5.2, "unit": "mmol/L", "ref_high": 5.2}, {"marker": "hdl", "value": 1.34, "unit": "mmol/L", "ref_low": 1.0},
            {"marker": "ldl", "value": 3.31, "unit": "mmol/L", "ref_high": 3.4}, {"marker": "tg", "value": 1.12, "unit": "mmol/L", "ref_high": 1.7},
            {"marker": "apob", "value": 0.96, "unit": "g/L", "ref_high": 1.3}, {"marker": "hba1c", "value": 5.4, "unit": "%", "ref_high": 5.6},
            {"marker": "glucose", "value": 5.1, "unit": "mmol/L", "ref_high": 6.0}, {"marker": "hscrp", "value": 0.9, "unit": "mg/L", "ref_high": 5.0}]}]))
    (M / "inbody.yaml").write_text(yaml_dump([
        {"date": "2026-07-28", "weight_kg": 82.1, "smm_kg": 35.1, "fat_kg": 19.2, "pbf_pct": 23.4, "ffm_kg": 62.9, "visceral_level": 9, "smi": 8.2, "bmr_kcal": 1730},
        {"date": "2026-10-13", "weight_kg": 79.0, "smm_kg": 35.4, "fat_kg": 16.0, "pbf_pct": 20.3, "ffm_kg": 63.0, "visceral_level": 7, "smi": 8.3, "bmr_kcal": 1734}]))
    (M / "tests.yaml").write_text(yaml_dump([
        {"date": "2026-08-02", "test": "grip", "left_kg": 43.5, "right_kg": 45.8}, {"date": "2026-10-17", "test": "grip", "left_kg": 45.1, "right_kg": 47.2},
        {"date": "2026-08-02", "test": "one_leg_stand", "seconds": 38}, {"date": "2026-10-17", "test": "one_leg_stand", "seconds": 52},
        {"date": "2026-08-02", "test": "waist", "cm": 92.0}, {"date": "2026-10-17", "test": "waist", "cm": 88.5},
        {"date": "2026-09-05", "test": "hr_cap_run", "speed_kmh": 9.0, "cap_bpm": 145, "km": 3.9, "minutes": 26},
        {"date": "2026-10-10", "test": "hr_cap_run", "speed_kmh": 9.0, "cap_bpm": 145, "km": 4.6, "minutes": 31}]))
    (M / "episodes.yaml").write_text(yaml_dump([{"start": "2026-09-02", "end": "2026-09-04", "what": "cold: sore throat, low energy"}]))
    (M / "supplements.yaml").write_text(yaml_dump([{"name": "Vitamin D3", "frequency": "daily", "started": "2026-10-05"}]))
    # totals for every day
    r = subprocess.run([sys.executable, str(CODE / "scripts" / "compute.py")], env={**os.environ, "FT_DATA": str(OUT)}, capture_output=True, text=True)
    bad = [l for l in r.stdout.splitlines() if "!!" in l]
    print(f"wrote {len(DAYS)} days to {OUT}; compute exit {r.returncode}; {len(bad)} day(s) with parse problems")
    for l in bad[:10]: print("  ", l)
    if r.returncode: print(r.stderr[-2000:])

if __name__ == "__main__":
    main()
