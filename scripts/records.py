"""Body Kaizen records: the one format every source is translated into before it reaches the day files.

A source adapter (source_garmin.py, later source_apple.py, ...) turns that source's own data into a list of records;
`to_day` turns a day's records into day-file fields, and `merge_into_day` writes them into a day file. Nothing after
this point needs to know which watch or app the data came from. See docs/iphone-sync.md, "The translation layer".

Records are plain dicts with a `kind`. Times are local wall-clock strings (`HH:MM`, or `YYYY-MM-DDTHH:MM` where a
date is needed) in the time zone the data was recorded in; durations are seconds; distances metres; energy kcal.
A field a source doesn't have is left out, never set to None.
"""

KINDS = {
    # one per night, dated by the morning it ended
    "night": {"asleep_s", "deep_s", "light_s", "rem_s", "awake_s", "start", "end", "score", "spo2_avg", "spo2_low",
              "respiration", "overnight_hr", "hrv_ms", "hrv_method", "hrv_7d_ms", "hrv_status"},
    # one per calendar day
    "day": {"steps", "energy_total", "energy_active", "energy_bmr", "intensity_moderate_min", "intensity_vigorous_min",
            "rhr", "body_battery", "stress_avg"},
    # one per session
    "workout": {"type", "mode", "start", "duration_s", "moving_s", "distance_m", "pool_m", "hr_avg", "hr_max",
                "kcal_total", "kcal_bmr", "cadence", "zones_s", "name", "source_id", "source_type"},
}
COMMON = {"kind", "source"}
WORKOUT_TYPES = {"run", "gym", "swim", "yoga", "walk", "ruck", "ride", "hike", "other"}
HRV_METHODS = {"rmssd", "sdnn"}
SOURCE_LABELS = {"garmin": "Garmin", "apple": "Apple Health"}


def check(rec):
    """Raise ValueError when a record isn't one of ours: unknown kind or field, missing source, a bad value."""
    kind = rec.get("kind")
    if kind not in KINDS: raise ValueError(f"unknown record kind {kind!r}")
    if not rec.get("source"): raise ValueError(f"{kind} record without a source")
    extra = set(rec) - KINDS[kind] - COMMON
    if extra: raise ValueError(f"{kind} record has unknown fields: {', '.join(sorted(extra))}")
    if kind == "workout" and rec.get("type") not in WORKOUT_TYPES: raise ValueError(f"unknown workout type {rec.get('type')!r}")
    if "hrv_ms" in rec and rec.get("hrv_method") not in HRV_METHODS: raise ValueError("HRV without its method (rmssd or sdnn)")
    for k, v in rec.items():
        if k in COMMON or k in ("type", "mode", "start", "end", "name", "source_id", "source_type", "hrv_method", "hrv_status"): continue
        if k == "zones_s":
            if not isinstance(v, dict) or any(z not in {"z1", "z2", "z3", "z4", "z5"} or not _num(n) for z, n in v.items()):
                raise ValueError("zones_s must map z1..z5 to seconds")
        elif not _num(v): raise ValueError(f"{kind}.{k} must be a number, got {v!r}")
    return rec


def _num(v): return isinstance(v, (int, float)) and not isinstance(v, bool)


def _put(d, k, v):
    if v is not None and v != "" and v != {}: d[k] = v


def _hm(secs):
    secs = int(round(secs)); return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"


def _clock(secs):
    secs = int(round(secs)); h, r = divmod(secs, 3600); m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def to_day(records):
    """A day's records -> the day-file fields they fill: steps, energy, intensity_min, recovery, sessions."""
    for r in records: check(r)
    night = next((r for r in records if r["kind"] == "night"), {})
    day = next((r for r in records if r["kind"] == "day"), {})
    out = {}
    _put(out, "steps", day.get("steps"))
    energy = {}
    for k, f in (("total", "energy_total"), ("active", "energy_active"), ("bmr", "energy_bmr")): _put(energy, k, day.get(f))
    _put(out, "energy", {k: round(v) for k, v in energy.items()})
    im = {}
    _put(im, "moderate", day.get("intensity_moderate_min")); _put(im, "vigorous", day.get("intensity_vigorous_min"))
    _put(out, "intensity_min", im)

    rec = {}
    if night.get("asleep_s"):
        rec["sleep"] = _hm(night["asleep_s"])
        stages = {}
        for name in ("deep", "light", "rem"):
            if night.get(f"{name}_s") is not None: stages[name] = round(night[f"{name}_s"] / 60)
        _put(rec, "sleep_stages_min", stages)
        if night.get("awake_s") is not None: rec["awake_min"] = round(night["awake_s"] / 60)
        if night.get("start") and night.get("end"):
            rec["in_bed"] = f"{night['start'][11:16]}–{night['end'][11:16]}"
            rec["sleep_start"] = night["start"]; rec["sleep_end"] = night["end"]
    for k in ("score",): _put(rec, "sleep_score", night.get(k))
    for k in ("spo2_avg", "spo2_low", "respiration", "overnight_hr", "hrv_ms", "hrv_7d_ms", "hrv_status"): _put(rec, k, night.get(k))
    if "hrv_ms" in night and night.get("hrv_method") != "rmssd": rec["hrv_method"] = night["hrv_method"]   # rmssd is the long-standing default
    for k in ("rhr", "body_battery", "stress_avg"): _put(rec, k, day.get(k))
    _put(out, "recovery", rec)

    sessions = []
    for w in (r for r in records if r["kind"] == "workout"):
        src, typ = w["source"], w["type"]
        e = {"type": typ, f"{src}_id": w.get("source_id"), "source": src}
        if typ == "other": e["note"] = f"{SOURCE_LABELS.get(src, src)}: {w.get('source_type') or 'other'}"
        _put(e, "mode", w.get("mode"))
        _put(e, "start", w.get("start"))
        if w.get("duration_s"): e["duration_min"] = round(w["duration_s"] / 60)
        dist = w.get("distance_m")
        if dist and typ in ("run", "walk", "ruck"):
            e["distance_km"] = round(dist / 1000, 2)
            if w.get("duration_s"): e["time"] = _clock(w["duration_s"])
            if w.get("moving_s"): e["moving_time"] = _clock(w["moving_s"])
            if typ == "run": e["distance_source"] = "watch" if w.get("mode") == "treadmill" else "gps"
        if dist and typ == "swim":
            e["distance_m"] = round(dist); _put(e, "pool_m", round(w["pool_m"]) if w.get("pool_m") else None)
        hr = {}
        _put(hr, "avg", round(w["hr_avg"]) if w.get("hr_avg") else None); _put(hr, "max", round(w["hr_max"]) if w.get("hr_max") else None)
        _put(e, "hr", hr)
        kc = {}
        if w.get("kcal_total"):
            kc["total"] = round(w["kcal_total"])
            if w.get("kcal_bmr"): kc["active"] = round(w["kcal_total"] - w["kcal_bmr"])
        _put(e, "kcal", kc)
        _put(e, "cadence", round(w["cadence"]) if w.get("cadence") else None)
        _put(e, "zones_min", {z: round(s / 60) for z, s in (w.get("zones_s") or {}).items() if s})
        _put(e, f"{src}_name", w.get("name") or None)
        sessions.append(e)
    out["sessions"] = sessions
    return out


# Fields the person may have set by hand that a source must never overwrite.
KEEP = {"lifts", "note", "effort", "rpe", "load_kg", "style", "stroke"}


def _mins(hhmm):
    try: h, m = map(int, str(hhmm).split(":")[:2]); return h * 60 + m
    except Exception: return None


def owns(owner, section, source):
    """Whether `source` may write `section` of a day already written by `owner`. A section with no owner, or one this
    source wrote, is always writable; another source's section only if settings.yaml `sources:` gives it to us."""
    if not owner or owner == source: return True
    try:
        import bkenv
        chosen = (bkenv.settings().get("sources") or {}).get(section)
    except Exception: chosen = None
    return chosen == source


def merge_into_day(day, mapped, source):
    """Merge one source's `to_day` output into a loaded day dict in place. Returns a short list of what changed.

    steps, energy, intensity minutes and recovery belong to one source per day (first come, unless settings.yaml
    `sources:` says otherwise); sessions are matched by the source's id, then by type and start time, so the same
    workout logged by hand, from Hevy and from a watch stays one session."""
    changes = []
    owner = lambda k: (day.get(k) or {}).get("source") if isinstance(day.get(k), dict) else day.get(f"{k}_source")
    if "steps" in mapped and day.get("steps") != mapped["steps"] and owns(day.get("steps_source"), "steps", source):
        day["steps"] = mapped["steps"]; changes.append("steps")
        if source != "garmin": day["steps_source"] = source
    for key in ("intensity_min", "fitness"):
        if key in mapped and day.get(key) != {**mapped[key], "source": source} and owns(owner(key), key, source):
            day[key] = {**mapped[key], "source": source}; changes.append(key.replace("_min", " minutes"))
    if "energy" in mapped and day.get("energy") != {**mapped["energy"], "source": source} and owns(owner("energy"), "energy", source):
        day["energy"] = {**mapped["energy"], "source": source}; changes.append("energy")
    if mapped.get("recovery") and owns(owner("recovery"), "recovery", source):
        rec = dict(day.get("recovery") or {})
        before = dict(rec)
        rec.update(mapped["recovery"]); rec["source"] = source
        if rec != before: day["recovery"] = rec; changes.append("recovery")
    idk = f"{source}_id"
    ex = day.setdefault("exercise", []) if mapped.get("sessions") else day.get("exercise", [])
    for g in mapped.get("sessions", []):
        match = next((e for e in ex if g.get(idk) and e.get(idk) == g[idk]), None)
        if not match:
            cands = [e for e in ex if e.get("type") == g["type"] and not e.get(idk)]
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
