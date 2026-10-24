"""Map raw Garmin Connect JSON (as saved by garmin_pull.py) into the day-file schema, and merge.

Kept separate from the network code so it can be tested against saved raw files and fixed
without re-pulling: rerun `garmin_pull.py --remap` after changing anything here.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bkenv  # noqa: E402

ACTIVITY_TYPES = {  # Garmin typeKey -> (our type, run mode)
    "running": ("run", "outdoor"), "street_running": ("run", "outdoor"), "track_running": ("run", "outdoor"),
    "treadmill_running": ("run", "treadmill"), "trail_running": ("run", "trail"), "indoor_running": ("run", "treadmill"),
    "strength_training": ("gym", None), "indoor_cardio": ("gym", None), "hiit": ("gym", None),
    "lap_swimming": ("swim", None), "open_water_swimming": ("swim", None), "swimming": ("swim", None),
    "yoga": ("yoga", None), "pilates": ("yoga", None),
    "walking": ("walk", None), "casual_walking": ("walk", None), "speed_walking": ("walk", None), "hiking": ("walk", None),
}

def _hm(secs):
    secs = int(round(secs)); return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"

def _clock(secs):
    secs = int(round(secs)); h, r = divmod(secs, 3600); m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _local_hhmm(ms_gmt):
    return dt.datetime.fromtimestamp(ms_gmt / 1000, tz=dt.timezone.utc).astimezone(bkenv.tz()).strftime("%H:%M")

def _put(d, k, v):
    if v is not None and v != "" and v != {}: d[k] = v

def map_day(raw):
    """raw = {"summary":..., "sleep":..., "hrv":..., "activities":[...]} -> {"steps", "energy", "recovery", "sessions"}"""
    out = {}
    s = raw.get("summary") or {}
    _put(out, "steps", s.get("totalSteps"))
    energy = {}
    _put(energy, "total", s.get("totalKilocalories")); _put(energy, "active", s.get("activeKilocalories")); _put(energy, "bmr", s.get("bmrKilocalories"))
    _put(out, "energy", {k: round(v) for k, v in energy.items()})
    im = {}
    _put(im, "moderate", s.get("moderateIntensityMinutes")); _put(im, "vigorous", s.get("vigorousIntensityMinutes"))
    _put(out, "intensity_min", im)

    rec = {}
    sl = (raw.get("sleep") or {}).get("dailySleepDTO") or {}
    if sl.get("sleepTimeSeconds"):
        rec["sleep"] = _hm(sl["sleepTimeSeconds"])
        stages = {}
        for k, name in (("deepSleepSeconds", "deep"), ("lightSleepSeconds", "light"), ("remSleepSeconds", "rem")):
            if sl.get(k) is not None: stages[name] = round(sl[k] / 60)
        _put(rec, "sleep_stages_min", stages)
        if sl.get("awakeSleepSeconds") is not None: rec["awake_min"] = round(sl["awakeSleepSeconds"] / 60)
        if sl.get("sleepStartTimestampGMT") and sl.get("sleepEndTimestampGMT"):   # GMT fields: local ones double-shift for UTC+8
            rec["in_bed"] = f"{_local_hhmm(sl['sleepStartTimestampGMT'])}–{_local_hhmm(sl['sleepEndTimestampGMT'])}"
            iso = lambda ms: dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).astimezone(bkenv.tz()).strftime("%Y-%m-%dT%H:%M")
            rec["sleep_start"] = iso(sl["sleepStartTimestampGMT"]); rec["sleep_end"] = iso(sl["sleepEndTimestampGMT"])
    _put(rec, "sleep_score", ((sl.get("sleepScores") or {}).get("overall") or {}).get("value"))
    _put(rec, "spo2_avg", sl.get("averageSpO2Value")); _put(rec, "spo2_low", sl.get("lowestSpO2Value"))
    _put(rec, "respiration", sl.get("averageRespirationValue"))
    _put(rec, "overnight_hr", sl.get("avgHeartRate") or sl.get("averageHeartRate"))
    hv = (raw.get("hrv") or {}).get("hrvSummary") or {}
    _put(rec, "hrv_ms", hv.get("lastNightAvg")); _put(rec, "hrv_7d_ms", hv.get("weeklyAvg"))
    if hv.get("status"): rec["hrv_status"] = str(hv["status"]).lower()
    _put(rec, "rhr", s.get("restingHeartRate") or (raw.get("sleep") or {}).get("restingHeartRate"))
    _put(rec, "body_battery", s.get("bodyBatteryChargedValue"))
    _put(rec, "stress_avg", s.get("averageStressLevel") if (s.get("averageStressLevel") or -1) >= 0 else None)
    _put(out, "recovery", rec)

    sessions = []
    for a in raw.get("activities") or []:
        key = ((a.get("activityType") or {}).get("typeKey") or "other").lower()
        typ, mode = ACTIVITY_TYPES.get(key, ("other", None))
        name = (a.get("activityName") or "")
        if typ == "walk" and "ruck" in name.lower(): typ = "ruck"
        e = {"type": typ, "garmin_id": a.get("activityId"), "source": "garmin"}
        if typ == "other": e["note"] = f"Garmin: {key}"
        _put(e, "mode", mode)
        if a.get("startTimeLocal"): e["start"] = str(a["startTimeLocal"])[11:16]
        if a.get("duration"): e["duration_min"] = round(a["duration"] / 60)
        dist = a.get("distance")
        if dist and typ in ("run", "walk", "ruck"):
            e["distance_km"] = round(dist / 1000, 2); e["time"] = _clock(a["duration"])
            if a.get("movingDuration"): e["moving_time"] = _clock(a["movingDuration"])
            if typ == "run": e["distance_source"] = "watch" if mode == "treadmill" else "gps"
        if dist and typ == "swim":
            e["distance_m"] = round(dist); _put(e, "pool_m", round(a["poolLength"]) if a.get("poolLength") else None)
        hr = {}
        _put(hr, "avg", round(a["averageHR"]) if a.get("averageHR") else None); _put(hr, "max", round(a["maxHR"]) if a.get("maxHR") else None)
        _put(e, "hr", hr)
        kc = {}
        if a.get("calories"):
            kc["total"] = round(a["calories"])
            if a.get("bmrCalories"): kc["active"] = round(a["calories"] - a["bmrCalories"])
        _put(e, "kcal", kc)
        _put(e, "cadence", round(a["averageRunningCadenceInStepsPerMinute"]) if a.get("averageRunningCadenceInStepsPerMinute") else None)
        zones = {f"z{i}": round(a[f"hrTimeInZone_{i}"] / 60) for i in range(1, 6) if a.get(f"hrTimeInZone_{i}")}
        _put(e, "zones_min", zones)
        _put(e, "garmin_name", name or None)
        sessions.append(e)
    out["sessions"] = sessions
    return out

# Fields the person may have set by hand that Garmin must never overwrite.
KEEP = {"lifts", "note", "effort", "rpe", "load_kg", "style", "stroke"}

def _mins(hhmm):
    try: h, m = map(int, str(hhmm).split(":")[:2]); return h * 60 + m
    except Exception: return None

def merge_day(day, mapped):
    """Merge mapped Garmin data into a loaded day dict in place. Returns a short list of what changed."""
    changes = []
    if "steps" in mapped and day.get("steps") != mapped["steps"]:
        day["steps"] = mapped["steps"]; changes.append("steps")
    for key in ("intensity_min", "fitness"):
        if key in mapped and day.get(key) != {**mapped[key], "source": "garmin"}:
            day[key] = {**mapped[key], "source": "garmin"}; changes.append(key.replace("_min", " minutes"))
    if "energy" in mapped and day.get("energy") != {**mapped["energy"], "source": "garmin"}:
        day["energy"] = {**mapped["energy"], "source": "garmin"}; changes.append("energy")
    if mapped.get("recovery"):
        rec = dict(day.get("recovery") or {})
        before = dict(rec)
        rec.update(mapped["recovery"]); rec["source"] = "garmin"
        if rec != before: day["recovery"] = rec; changes.append("recovery")
    ex = day.setdefault("exercise", []) if mapped.get("sessions") else day.get("exercise", [])
    for g in mapped.get("sessions", []):
        match = next((e for e in ex if g.get("garmin_id") and e.get("garmin_id") == g["garmin_id"]), None)
        if not match:
            cands = [e for e in ex if e.get("type") == g["type"] and not e.get("garmin_id")]
            gs = _mins(g.get("start"))
            timed = [e for e in cands if _mins(e.get("start")) is not None and gs is not None]
            close = [e for e in timed if abs(_mins(e["start"]) - gs) <= 90]
            match = close[0] if close else (next((e for e in cands if e.get("start") is None), None))
        if match:
            before = dict(match)
            belt = match.get("distance_source") == "belt"
            for k, v in g.items():
                if k in KEEP and match.get(k): continue
                if belt and k in ("distance_km", "time", "moving_time", "distance_source"): continue   # belt distance beats the watch
                if isinstance(v, dict) and isinstance(match.get(k), dict):
                    match[k] = {**match[k], **v}      # merge hr/kcal/zones; keep e.g. a hand-entered recovery HR
                else:
                    match[k] = v
            if match != before: changes.append(f"{g['type']} updated")
        else:
            ex.append(g); changes.append(f"{g['type']} added")
    if not day.get("exercise"): day.pop("exercise", None)
    return changes
