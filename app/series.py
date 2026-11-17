"""Detail data behind the day files: sleep stages, the day's step and body-battery timelines, workout traces, and the
few figures only one source has (Garmin's sleep need, fitness age, body battery).

Pages ask this module, never a source's own files, so a new source (the iPhone app's Apple Health cache) only has to
be taught here. Times come back as timezone-aware UTC datetimes; `minutes(t, day)` places one on a day.

Two sources so far: Garmin's raw files (imports/garmin/, saved by scripts/garmin_pull.py) and the iPhone app's detail
files (imports/apple/, written by scripts/apple_import.py from Apple Health). Where both have something, settings.yaml
`sources:` decides (e.g. `sources: {sleep: apple}`); otherwise Garmin, the first connected, comes first.
"""
import datetime as dt, json

import data

STAGES = {0: "deep", 1: "light", 2: "rem", 3: "awake"}


def _garmin_day(day):
    try: return json.loads((data.ROOT / "imports" / "garmin" / day[:4] / f"{day}.json").read_text(encoding="utf-8"))
    except Exception: return {}


def _apple_day(day):
    try: return json.loads((data.ROOT / "imports" / "apple" / day[:4] / f"{day}.json").read_text(encoding="utf-8"))
    except Exception: return {}


def _order(section):
    """Which source to ask first for `section`: settings.yaml `sources:` if it names one, else Garmin."""
    try: chosen = (data.bkenv.settings().get("sources") or {}).get(section)
    except Exception: chosen = None
    return ("apple", "garmin") if chosen == "apple" else ("garmin", "apple")


def _first(section, **by_source):
    """The first source (in `_order`) whose reader returns something."""
    for src in _order(section):
        got = by_source[src]()
        if got: return got
    return by_source[_order(section)[0]]()


def _utc(v):
    """A source timestamp (epoch milliseconds, or an ISO string in UTC) -> aware UTC datetime."""
    if isinstance(v, dt.datetime): return v.astimezone(dt.timezone.utc)
    if isinstance(v, (int, float)): return dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc)
    return dt.datetime.fromisoformat(str(v)[:19]).replace(tzinfo=dt.timezone.utc)


def minutes(t, day):
    """A timestamp -> whole minutes from the local midnight that starts `day` (negative the evening before)."""
    t = _utc(t).astimezone(data.bkenv.tz()).replace(tzinfo=None)
    return int((t - dt.datetime.combine(dt.date.fromisoformat(day), dt.time())).total_seconds() // 60)


def stamp(day):
    """Something that changes whenever the detail data for `day` changes (for caches)."""
    out = []
    for src in ("garmin", "apple"):
        try: out.append((data.ROOT / "imports" / src / day[:4] / f"{day}.json").stat().st_mtime)
        except OSError: pass
    return max(out) if out else None


# ---------- sleep ----------

def sleep_stages(day):
    """The night that ended on the morning of `day`, as [(start, end, stage)] with stage deep/light/rem/awake, or
    asleep where the source recorded sleep without stages (Apple's "asleep, unspecified")."""
    def garmin():
        out = []
        for x in ((_garmin_day(day).get("sleep") or {}).get("sleepLevels") or []):
            try: out.append((_utc(x["startGMT"]), _utc(x["endGMT"]), STAGES.get(int(x.get("activityLevel", 1)), "light")))
            except Exception: continue
        return out
    def apple():
        out = []
        for a, b, k in _apple_day(day).get("sleep") or []:
            try: out.append((_utc(a), _utc(b), k))
            except Exception: continue
        return out
    return _first("recovery", garmin=garmin, apple=apple)


def sleep_need(day, tonight=False):
    """Garmin's sleep need for the night that ended on `day` (or, with tonight=True, the night after it), as Garmin's
    own record ({actual, baseline, trainingFeedback, ...}); None without one. Only Garmin has this."""
    dto = (_garmin_day(day).get("sleep") or {}).get("dailySleepDTO") or {}
    return dto.get("nextSleepNeed" if tonight else "sleepNeed")


# ---------- the day ----------

def day_extras(day):
    """Day-level figures beyond the day file, each None when the source doesn't have it:
    steps, stress_avg, active_kcal, bmr_kcal, total_kcal, synced_to (local 'YYYY-MM-DDTHH:MM', how far the day is
    covered), body_battery_now, intensity_goal (per week), last_sync (UTC date 'YYYY-MM-DD')."""
    s = _garmin_day(day).get("summary") or {}
    ax = _apple_day(day).get("extras") or {}
    if ax and (not s or _order("steps")[0] == "apple"):   # Apple has no stress, body battery or weekly goal
        return {"steps": ax.get("steps"), "stress_avg": None, "active_kcal": ax.get("active_kcal"), "bmr_kcal": ax.get("bmr_kcal"),
                "total_kcal": ax.get("total_kcal"), "synced_to": ax.get("synced_to"), "body_battery_now": None,
                "intensity_goal": None, "last_sync": None}
    end = s.get("wellnessEndTimeLocal")
    return {"steps": s.get("totalSteps"), "stress_avg": s.get("averageStressLevel"), "active_kcal": s.get("activeKilocalories"),
            "bmr_kcal": s.get("bmrKilocalories"), "total_kcal": s.get("totalKilocalories"), "synced_to": end[:16] if end else None,
            "body_battery_now": s.get("bodyBatteryMostRecentValue"), "intensity_goal": s.get("intensityMinutesGoal"),
            "last_sync": (s.get("lastSyncTimestampGMT") or "")[:10] or None}


def steps_timeline(day):
    """[(time, steps)] in 15-minute blocks over the day."""
    return _first("steps", garmin=lambda: [(_utc(t), v) for t, v in _garmin_day(day).get("steps_intraday") or []],
                  apple=lambda: [(_utc(t), v) for t, v in _apple_day(day).get("steps") or []])


def heart_rate(day):
    """[(time, bpm)] per minute over the day. Apple only: Garmin's pull has no all-day heart rate."""
    return [(_utc(t), v) for t, v in _apple_day(day).get("hr") or []]


def glucose(day):
    """[(time, mmol/L)] from Apple Health (a CGM or meter writing into it). The Libre pull has its own files (glucose.py)."""
    return [(_utc(t), v) for t, v in _apple_day(day).get("glucose") or []]


def body_battery_timeline(day):
    """[(time, level)] over the day. Garmin only."""
    return [(_utc(t), v) for t, v in _garmin_day(day).get("body_battery_intraday") or []]


def recent_days(n=7):
    """The newest `n` days that have detail data, newest first."""
    days = set()
    for src in ("garmin", "apple"):
        days |= {p.stem for p in (data.ROOT / "imports" / src).glob("[0-9][0-9][0-9][0-9]/*.json")}
    return sorted(days, reverse=True)[:n]


def fitness_age():
    """{date: {fitnessAge, achievableFitnessAge, ...}} from Garmin, or {}."""
    p = data.ROOT / "imports" / "garmin" / "fitness_age.json"
    try: return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception: return {}


# ---------- workouts ----------

def workout_detail(e, day=None):
    """The saved detail for a logged session: {samples: [[epoch ms, hr, ...]], laps: [{distance_m, duration_s, ...}],
    summary: {recoveryHeartRate, activityTrainingLoad, ...}, aerobic_te, anaerobic_te, te_label, body_battery_change};
    None if the session has none. An Apple workout has samples only, and needs the session's `day` to be found."""
    aid = (e or {}).get("garmin_id")
    if aid:
        try: return json.loads((data.ROOT / "imports" / "garmin" / "activities" / f"{aid}.json").read_text(encoding="utf-8"))
        except Exception: pass
    uid = (e or {}).get("apple_id")
    if uid and day: return ((_apple_day(str(day)).get("workouts") or {}).get(uid)) or None
    return None
