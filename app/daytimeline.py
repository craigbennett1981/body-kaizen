"""Everything logged on one day, placed at its clock time: sleep, training, food, BP, symptoms, glucose."""
import datetime as dt, json
import data

STAGE = {0: "deep", 1: "light", 2: "rem", 3: "awake"}
STAGE_LABEL = {"deep": "Deep", "light": "Light", "rem": "REM", "awake": "Awake"}

def _raw(day):
    try: return json.loads((data.ROOT / "imports" / "garmin" / day[:4] / f"{day}.json").read_text())
    except Exception: return {}

def _gmt_min(v, day):
    """GMT timestamp (ISO string or epoch ms) -> minutes from local midnight of `day`."""
    if isinstance(v, (int, float)): t = dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc)
    else: t = dt.datetime.fromisoformat(str(v)[:19]).replace(tzinfo=dt.timezone.utc)
    t = t.astimezone(data.bkenv.tz()).replace(tzinfo=None)
    return int((t - dt.datetime.combine(dt.date.fromisoformat(day), dt.time())).total_seconds() // 60)

def _stages(raw, day):
    out = []
    for x in ((raw.get("sleep") or {}).get("sleepLevels") or []):
        try: s, e = _gmt_min(x["startGMT"], day), _gmt_min(x["endGMT"], day)
        except Exception: continue
        if e <= 0 or s >= 1440: continue
        k = STAGE.get(int(x.get("activityLevel", 1)), "light")
        out.append({"lane": "Sleep", "kind": "sleep_" + k, "start": max(0, s), "end": min(1440, e), "label": STAGE_LABEL[k], "detail": f"{e - s} min"})
    return out

def _hm(s):
    s = str(s or "")[:5]
    try: dt.datetime.strptime(s, "%H:%M"); return s
    except ValueError: return None

def _iso_to_hm(iso, day):
    """'2026-10-15T23:00' -> minutes from the day's midnight (negative if the night before)."""
    t = dt.datetime.fromisoformat(str(iso)[:16])
    return int((t - dt.datetime.combine(dt.date.fromisoformat(day), dt.time())).total_seconds() // 60)

def build(day):
    p = data.ROOT / "days" / day[:4] / f"{day}.yaml"
    if not p.exists(): return {"date": day, "events": [], "untimed": 0}
    d = data._jsonable(data._load(p))
    det = data.day_detail(day) or {}
    ev, untimed = [], 0
    m = lambda hm: int(hm[:2]) * 60 + int(hm[3:5])
    # sleep: last night (ends this morning) and tonight (starts this evening, from tomorrow's file)
    r = d.get("recovery") or {}
    raw = _raw(day)
    nxt = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    stages = _stages(raw, day) + _stages(_raw(nxt), day)
    ev += stages
    if not stages and r.get("sleep_start") and r.get("sleep_end"):
        ev.append({"lane": "Sleep", "kind": "sleep", "start": max(0, _iso_to_hm(r["sleep_start"], day)), "end": _iso_to_hm(r["sleep_end"], day),
                   "label": f"Sleep {r.get('sleep', '')}".strip(), "detail": f"score {r['sleep_score']}" if r.get("sleep_score") else ""})
    nxt = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    pn = data.ROOT / "days" / nxt[:4] / f"{nxt}.yaml"
    if pn.exists() and not any(e["start"] > 720 for e in stages):
        rn = (data._load(pn) or {}).get("recovery") or {}
        if rn.get("sleep_start"):
            s = _iso_to_hm(rn["sleep_start"], day)
            if s < 1440: ev.append({"lane": "Sleep", "kind": "sleep", "start": s, "end": 1440, "label": "Bed", "detail": ""})
    # training
    for e in d.get("exercise") or []:
        st = _hm(e.get("start"))
        if not st: continue
        dur = e.get("duration_min") or (e.get("duration_s") or 0) // 60 or (50 if e.get("type") == "gym" else 30)
        bits = []
        if e.get("distance_km"): bits.append(f"{e['distance_km']} km")
        if (e.get("hr") or {}).get("avg"): bits.append(f"HR {e['hr']['avg']}")
        if e.get("lifts"): bits.append(f"{len(e['lifts'])} lifts")
        kact, kgar = (e.get("kcal") or {}).get("active"), bool(e.get("garmin_id"))
        if not kact:
            try:
                est_total, _ = data.session_energy(e, data._targets_file().get("energy_estimates", {}))
                kact = round(est_total - int(dur) * 1.4) if est_total else None; kgar = False
            except Exception: kact = None
        ev.append({"lane": "Training", "kind": e.get("type", "other"), "start": m(st), "end": m(st) + int(dur), "kcal_active": kact, "kcal_garmin": kgar,
                   "label": (e.get("hevy_name") or e.get("name") or e.get("type", "")).title() if e.get("type") == "gym" else e.get("type", "").title(),
                   "detail": " · ".join(bits)})
    # food
    for meal, items in (det.get("meals") or {}).items():
        for it in items or []:
            st = _hm(it.get("time"))
            kcal = round(sum((c.get("macros") or {}).get("k", 0) for c in it.get("parsed") or []))
            prot = round(sum((c.get("macros") or {}).get("p", 0) for c in it.get("parsed") or []), 1)
            sfat = round(sum((c.get("macros") or {}).get("sf", 0) for c in it.get("parsed") or []), 1)
            if not st: untimed += 1; continue
            ev.append({"lane": "Food", "kind": "food", "start": m(st), "label": it.get("raw", ""), "kcal": kcal, "protein": prot, "satfat": sfat,
                       "meal": meal, "approx": bool(it.get("time_approx"))})
    # blood pressure
    for b in ((d.get("vitals") or {}).get("bp") or []):
        st = _hm(b.get("time"))
        if st: ev.append({"lane": "Health", "kind": "bp", "start": m(st), "label": f"BP {b['sys']}/{b['dia']}", "detail": f"pulse {b['pulse']}" if b.get("pulse") else ""})
    # weigh-in
    w = d.get("weight") or {}
    st = _hm(w.get("time"))
    if w.get("kg") and st:
        bits = [f"{w['bf_pct']}% fat" if w.get("bf_pct") else "", "fasted" if w.get("fasted") else "not fasted" if w.get("fasted") is False else ""]
        ev.append({"lane": "Health", "kind": "weight", "start": m(st), "label": f"Weight {w['kg']} kg", "detail": " · ".join(b for b in bits if b)})
    # symptoms / feel
    for s in d.get("symptoms") or []:
        st = _hm(s.get("time"))
        if st: ev.append({"lane": "Health", "kind": "symptom", "start": m(st), "label": str(s.get("what", "")), "detail": str(s.get("severity", ""))})
    try:
        import glucose
        g = glucose.day(day)
    except Exception:
        g = None
    # protein so far vs an even pace from waking to 21:00
    pmin = (det.get("targets") or {}).get("protein_min")
    food = sorted((e for e in ev if e["kind"] == "food"), key=lambda e: e["start"])
    protein = None
    if pmin and food:
        wake = max((e["end"] for e in ev if e["lane"] == "Sleep" and e["end"] < 720), default=None) or 7 * 60
        cum, pts = 0, [[wake, 0]]
        for e in food:
            cum += e.get("protein") or 0
            pts.append([e["start"], round(cum, 1)])
        protein = {"target": pmin, "wake": wake, "by": 21 * 60, "points": pts, "untimed": round(sum(
            sum((c.get("macros") or {}).get("p", 0) for c in it.get("parsed") or []) for items in (det.get("meals") or {}).values() for it in items or [] if not _hm(it.get("time"))), 1)}
    # watch intraday: body battery and 15-min steps
    bb = [[_gmt_min(t, day), v] for t, v in raw.get("body_battery_intraday") or [] if v is not None]
    steps = [[_gmt_min(t, day), v] for t, v in raw.get("steps_intraday") or [] if v]
    bb = [p for p in bb if 0 <= p[0] < 1440]; steps = [p for p in steps if 0 <= p[0] < 1440]
    calories = _calories(day, d, raw, ev, steps)
    return {"date": day, "events": sorted(ev, key=lambda e: e["start"]), "untimed": untimed, "glucose": g, "calories": calories,
            "protein": protein, "body_battery": bb, "steps": steps,
            "bp_untimed": sum(1 for b in ((d.get("vitals") or {}).get("bp") or []) if not _hm(b.get("time")))}


def _bmr_per_min(day):
    """Garmin's resting burn per minute: from this day's synced total if it covers enough of the day, else the latest full day."""
    for back in range(0, 8):
        dd = (dt.date.fromisoformat(day) - dt.timedelta(days=back)).isoformat()
        sm = (_raw(dd).get("summary") or {})
        bmr, end = sm.get("bmrKilocalories"), sm.get("wellnessEndTimeLocal")
        if not bmr or not end: continue
        mins = min(1440, _iso_to_hm(end, dd))
        if mins >= 240: return bmr / mins, back == 0
    return 1720 / 1440, False

def _calories(day, d, raw, ev, steps):
    """Cumulative calories eaten (at meal times) and burnt (Garmin's total spread over the day by resting rate,
    steps and workouts). Burn is exact at the last watch sync and estimated after it."""
    food = sorted((e for e in ev if e["kind"] == "food"), key=lambda e: e["start"])
    eaten, cum = [[0, 0]], 0
    for e in food:
        cum += e.get("kcal") or 0
        eaten.append([e["start"], round(cum)])
    sm = raw.get("summary") or {}
    rate, _ = _bmr_per_min(day)
    sync = None
    if sm.get("wellnessEndTimeLocal") and sm.get("totalKilocalories"):
        sync = max(0, min(1440, _iso_to_hm(sm["wellnessEndTimeLocal"], day)))
    now = data.bkenv.now()
    today = now.date().isoformat() == day
    end = (now.hour * 60 + now.minute) if today else 1440
    # extra (non-resting) burn per 15-min bin: workouts at their times, the rest by steps
    bins = [0.0] * 96
    workouts = [e for e in ev if e["lane"] == "Training" and e.get("end") is not None]
    work_kcal = 0
    for e in workouts:
        k = e.get("kcal_active")
        if not k: continue
        span = max(1, e["end"] - e["start"])
        for m in range(e["start"], min(1440, e["end"])):
            bins[m // 15] += k / span
        if e.get("kcal_garmin"): work_kcal += k   # already inside Garmin's active total
    if sync is not None:
        active = max(0, (sm.get("activeKilocalories") or 0) - work_kcal)
        total_steps = sum(v for m, v in steps if m < sync) or 0
        if total_steps:
            for m, v in steps:
                if m < sync: bins[m // 15] += active * v / total_steps
        elif active:
            for b in range(min(96, sync // 15)): bins[b] += active / max(1, sync // 15)
    else:   # no watch: walking from the day's step count (if any) spread over waking hours, plus logged sessions
        walk = (d.get("steps") or 0) * 0.045
        for b in range(28, 88): bins[b] += walk / 60
    burnt, cum = [[0, 0]], 0.0
    for b in range(96):
        m0 = b * 15
        if m0 >= end: break
        mins = min(15, end - m0)
        extra = bins[b] if (sync is None or m0 < sync) else 0
        cum += rate * mins + extra * (mins / 15)
        burnt.append([m0 + mins, round(cum)])
    if sync is not None and sync > 0:   # pin to Garmin's exact total at the sync time
        at = next((v for m, v in burnt if m >= sync), None)
        if at:
            scale = sm["totalKilocalories"] / at
            burnt = [[m, round(v * scale) if m <= sync else v + round(sm["totalKilocalories"] - at)] for m, v in burnt]
    return {"eaten": eaten, "burnt": burnt, "sync": sync, "garmin_total": sm.get("totalKilocalories") if sync is not None else None,
            "burnt_now": burnt[-1][1] if burnt else None, "eaten_now": eaten[-1][1], "estimated_after": sync if sync is not None and sync < end else None,
            "source": "garmin" if sync is not None else "estimate"}
