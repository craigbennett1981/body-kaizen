"""Read-only view of the repo's YAML data for the dashboard. No database: files are the truth."""
import datetime as dt, importlib, json, pathlib, re, sys, threading, yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import bkenv  # noqa: E402
ROOT = bkenv.DATA   # your data folder (FT_DATA); code paths use bkenv.CODE
import nutrition as N  # noqa: E402

_cache = {}
_foods_mtime = None

def _load(path):
    m = path.stat().st_mtime
    hit = _cache.get(path)
    if hit and hit[0] == m:
        return hit[1]
    d = yaml.safe_load(path.read_text()) or {}
    _cache[path] = (m, d)
    return d

def _s(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v

def _jsonable(o):
    if isinstance(o, dict): return {str(_s(k)): _jsonable(v) for k, v in o.items()}
    if isinstance(o, list): return [_jsonable(v) for v in o]
    return _s(o)

_nlock = threading.Lock()

def _nutrition(force=False):
    """The food matcher, reloaded when the food files change. Locked so two requests can't reload it at once
    (a half-finished reload once left a new food missing until restart)."""
    global _foods_mtime
    with _nlock:
        files = [ROOT / f for f in ("foods.yaml", "overrides.yaml", "meals.yaml", "settings.yaml")] + [N.STARTER_PATH]
        m = sum(f.stat().st_mtime for f in files if f.exists())
        if force or (_foods_mtime is not None and m != _foods_mtime):
            importlib.reload(N)
        _foods_mtime = m
    return N

def day_files():
    return sorted((ROOT / "days").rglob("*.yaml"))

def get_day(date):
    p = ROOT / "days" / date[:4] / f"{date}.yaml"
    return _jsonable(_load(p)) if p.exists() else None

# ---------- targets ----------
def _targets_file():
    return _load(ROOT / "targets.yaml")

def _blocks():
    return sorted(_targets_file()["intake"], key=lambda b: str(b["from"]))

def weight_target_for(date):
    kg = None
    for w in sorted(_targets_file().get("weight", []), key=lambda b: str(b["from"])):
        if str(w["from"]) <= date: kg = w["kg"]
    return kg

def reference():
    return _targets_file().get("reference", {})

def targets_for(date, day_type):
    blocks = _blocks()
    blk = None
    for b in blocks:
        if str(b["from"]) <= date: blk = b
    if not blk: return {}
    k = blk.get("kcal", {})
    kcal = k.get(day_type) or k.get("all") or k.get("training")
    out = {"label": blk.get("label"), "from": str(blk["from"]), "kcal": kcal}
    if "protein_g" in blk: out["protein_min"] = blk["protein_g"].get("min")
    if "satfat_g" in blk: out["satfat_max"] = blk["satfat_g"].get("max")
    if "fibre_g" in blk: out["fibre_min"] = blk["fibre_g"].get("min")
    if "fat_g" in blk: out["fat"] = blk["fat_g"]
    if "carbs_g" in blk: out["carbs"] = blk["carbs_g"]
    return out

def evaluate(totals, tgt, status):
    """ok True/False per metric; None when the day isn't complete or no target exists."""
    if not totals: return {}
    judge = status == "complete"
    ev = {}
    def put(name, val, lo=None, hi=None):
        d = "under" if lo is not None and val < lo else "over" if hi is not None and val > hi else None
        ev[name] = {"value": val, "ok": ((d is None) if judge else None), "dir": d}   # dir shown even on partial days
    t = totals
    if tgt.get("kcal"): put("kcal", t["kcal"], *tgt["kcal"])
    if tgt.get("protein_min"): put("protein_g", t["protein_g"], lo=tgt["protein_min"])
    if tgt.get("satfat_max"): put("satfat_g", t["satfat_g"], hi=tgt["satfat_max"])
    if tgt.get("fibre_min"): put("fibre_g", t["fibre_g"], lo=tgt["fibre_min"])
    if tgt.get("fat"): put("fat_g", t["fat_g"], *tgt["fat"])
    if tgt.get("carbs"): put("carbs_g", t["carbs_g"], *tgt["carbs"])
    return ev

# ---------- summaries ----------
def summary():
    out = []
    for p in day_files():
        d = _jsonable(_load(p))
        date, dtp = d["date"], d.get("day_type", "rest")
        tgt = targets_for(date, dtp)
        tgt["weight_kg"] = weight_target_for(date)
        ex = d.get("exercise") or []
        out.append({
            "date": date, "status": d.get("status"), "day_type": dtp, "note": d.get("note"),
            "totals": d.get("totals"), "targets": tgt, "eval": evaluate(d.get("totals"), tgt, d.get("status")),
            "weight": d.get("weight"), "recovery": d.get("recovery"), "vitals": d.get("vitals"),
            "feel": d.get("feel"), "steps": d.get("steps"),
            # Garmin's total burn, only when the watch was clearly worn (on watch-off days Garmin reports resting burn alone)
            "burn": (d.get("energy") or {}).get("total") if (d.get("energy") or {}).get("source") == "garmin" and (d.get("steps") or 0) >= 1500 else None,
            "exercise": [{k: e.get(k) for k in ("type", "effort", "distance_km", "time", "start", "duration_min") if e.get(k) is not None} for e in ex],
        })
    return out

def day_detail(date):
    d = get_day(date)
    if not d: return None
    n = _nutrition()
    items_ = [c.get("item") for its in (d.get("meals") or {}).values() for it in its or [] for c in it.get("parsed") or []]
    if any(i not in n.FOODS for i in items_): n = _nutrition(force=True)   # a food added since the last reload
    for meal, items in (d.get("meals") or {}).items():
        for it in items or []:
            for c in it.get("parsed") or []:
                if c.get("item") not in n.FOODS: continue   # unknown food: shown unresolved rather than failing the page
                m = n.macros(c)
                c["macros"] = {k: round(v, 1) for k, v in m.items() if v}
                c["name"] = n.FOODS.get(c["item"], {}).get("name", c["item"])
    tgt = targets_for(date, d.get("day_type", "rest"))
    d["targets"] = tgt
    d["eval"] = evaluate(d.get("totals"), tgt, d.get("status"))
    try:   # personal bests set on this day (estimated 1-rep max above every earlier session), for the stars in the Training panel
        tr = training()
        d["prs"] = {lift: {k: p.get(k) for k in ("kg", "reps", "metres")} for lift, pts in tr["lifts"].items()
                    for p in pts if p["date"] == date and p.get("pr") and len(pts) > 1}
    except Exception:
        d["prs"] = {}
    return d

# ---------- training ----------
SET_KG = re.compile(r"^([\d.]+)x(\d+)$")
SET_CARRY = re.compile(r"^([\d.]+)kg@(\d+)m$")

ENERGY_TYPES = ["gym", "run", "swim", "ruck", "yoga", "walk"]

def session_energy(e, est):
    """(kcal, estimated?) for one session; None when it can't be sensibly estimated (walks, scooter)."""
    k = (e.get("kcal") or {}).get("total")
    if k: return k, False
    t = e.get("type")
    if t == "gym": return est["gym_kcal"], True
    if t == "run": return round(e["distance_km"] * est["run_kcal_per_km"]) if e.get("distance_km") else est["run_kcal_default"], True
    if t == "swim": return round(e["distance_m"] * est["swim_kcal_per_m"]) if e.get("distance_m") else est["swim_kcal_default"], True
    if t == "ruck": return round(e.get("distance_km", 6) * est["ruck_kcal_per_km"]), True
    if t == "yoga": return est["yoga_kcal"], True
    return None, False

def energy():
    est = _targets_file().get("energy_estimates", {})
    out = []
    for p in day_files():
        d = _jsonable(_load(p))
        sessions = []
        for e in d.get("exercise") or []:
            if e.get("type") == "walk": continue   # walking energy comes from steps, so a logged walk would double count
            k, is_est = session_energy(e, est)
            if k is None: continue
            bits = []
            if e.get("distance_km"): bits.append(f"{e['distance_km']} km")
            if e.get("distance_m"): bits.append(f"{e['distance_m']} m")
            if e.get("time"): bits.append(str(e["time"]))
            if e.get("duration_min"): bits.append(f"{e['duration_min']} min")
            sessions.append({"type": e["type"] if e["type"] in ENERGY_TYPES and e["type"] != "walk" else "other", "kcal": k, "estimated": is_est,
                             "desc": ", ".join(bits), "effort": e.get("effort")})
        steps = d.get("steps")
        if steps:
            # walking energy from steps, minus steps already counted inside runs and rucks
            sub = sum((e.get("distance_km") or 0) * est.get("run_steps_per_km", 1000) for e in d.get("exercise") or [] if e.get("type") == "run")
            sub += sum((e.get("distance_km") or 0) * est.get("ruck_steps_per_km", 1300) for e in d.get("exercise") or [] if e.get("type") == "ruck")
            walk_steps = max(0, steps - sub)
            sessions.append({"type": "walk", "kcal": round(walk_steps * est.get("step_kcal", 0.045)), "estimated": True,
                             "desc": f"{walk_steps:,.0f} walking steps" + (f" (of {steps:,})" if sub else "")})
        out.append({"date": d["date"], "sessions": sessions, "steps": steps})
    return {"types": ENERGY_TYPES + ["other"], "days": out, "estimates": est, "steps_ref": reference().get("steps_daily")}

def _act_hrr(aid):
    """The watch's recovery heart rate for an activity, from its saved Garmin detail file (if fetched)."""
    if not aid: return None
    try: return (json.loads((ROOT / "imports" / "garmin" / "activities" / f"{aid}.json").read_text()).get("summary") or {}).get("recoveryHeartRate")
    except Exception: return None

def training():
    lifts, runs = {}, []
    epochs = _load(ROOT / "exercises.yaml")
    # equipment changes: the latest epoch with a `from` date splits progress into before / after (any epoch names)
    froms = sorted(str(v["from"]) for v in (epochs.get("epochs") or {}).values() if isinstance(v, dict) and v.get("from"))
    swap = froms[-1] if froms else None
    epoch_lifts = {k for k, v in (epochs.get("lifts") or {}).items() if v.get("epochs")}
    for p in day_files():
        d = _jsonable(_load(p)); date = d["date"]
        for e in d.get("exercise") or []:
            if e.get("type") == "gym":
                for l in e.get("lifts") or []:
                    best = None
                    for s in l.get("sets") or []:
                        s = str(s); m = SET_KG.match(s); c = SET_CARRY.match(s)
                        if m:
                            w, r = float(m.group(1)), int(m.group(2))
                            cand = {"kg": w, "reps": r, "e1rm": round(w * (1 + r / 30), 1)}
                        elif c:
                            cand = {"kg": float(c.group(1)), "metres": int(c.group(2)), "e1rm": float(c.group(1))}
                        else:
                            continue
                        if best is None or cand["e1rm"] > best["e1rm"]: best = cand
                    if best:
                        best["date"] = date
                        best["epoch"] = ("v2" if date >= swap else "v1") if swap and l["ex"] in epoch_lifts else None
                        lifts.setdefault(l["ex"], []).append(best)
            if e.get("type") == "run" and e.get("distance_km") and e.get("time"):
                parts = [int(x) for x in str(e["time"]).split(":")]
                secs = parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
                hr = e.get("hr") or {}
                runs.append({"date": date, "km": e["distance_km"], "secs": secs, "pace": round(secs / e["distance_km"]),
                             "avg_hr": hr.get("avg"), "max_hr": hr.get("max"), "hrr": None if e.get("hrr_invalid") else (hr.get("recovery") or _act_hrr(e.get("garmin_id"))), "effort": e.get("effort"),
                             "mode": e.get("mode"), "temp_c": e.get("temp_c")})
    for ex, pts in lifts.items():
        top = 0
        for pt in pts:
            pt["pr"] = pt["e1rm"] > top
            top = max(top, pt["e1rm"])
    return {"lifts": lifts, "runs": runs, "machine_swap": swap, "reference": reference(), "energy": energy()}

def body():
    scale = []
    for p in day_files():
        d = _jsonable(_load(p))
        w = d.get("weight")
        if w and w.get("kg"):
            scale.append({"date": d["date"], **{k: w.get(k) for k in ("kg", "fasted", "bf_pct", "muscle_kg", "ffm_kg", "note")}})
    inbody = _jsonable(yaml.safe_load((ROOT / "measurements" / "inbody.yaml").read_text()))
    wt = [{"date": str(w["from"]), "kg": w["kg"], "source": w.get("source")} for w in sorted(_targets_file().get("weight", []), key=lambda b: str(b["from"]))]
    return {"scale": scale, "inbody": inbody, "weight_targets": wt, "bp": bp_readings()}

def bp_category(sys_, dia):
    """2017 ACC/AHA adult categories."""
    if sys_ >= 180 or dia >= 120: return "crisis"
    if sys_ >= 140 or dia >= 90: return "stage 2"
    if sys_ >= 130 or dia >= 80: return "stage 1"
    if sys_ >= 120: return "elevated"
    return "normal"

def bp_readings():
    morning_before = ((_load(ROOT / "settings.yaml").get("vitals") or {}).get("bp") or {}).get("morning_before", "09:00")
    out = []
    for p in day_files():
        d = _jsonable(_load(p))
        for b in ((d.get("vitals") or {}).get("bp") or []):
            if not (b.get("sys") and b.get("dia")): continue
            ctx = b.get("context") or (("morning" if str(b["time"]) < morning_before else "other") if b.get("time") else "unspecified")
            out.append({"date": d["date"], "time": b.get("time"), "sys": b["sys"], "dia": b["dia"], "pulse": b.get("pulse"),
                        "context": ctx, "category": bp_category(b["sys"], b["dia"]), "note": b.get("note")})
    return out
