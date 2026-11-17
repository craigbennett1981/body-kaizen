"""Detail data behind the day files: sleep stages, the day's step and body-battery timelines, workout traces, and the
few figures only one source has (Garmin's sleep need, fitness age, body battery).

Pages ask this module, never a source's own files, so a new source (the iPhone app's Apple Health cache) only has to
be taught here. Times come back as timezone-aware UTC datetimes; `minutes(t, day)` places one on a day.

Today everything here is read from Garmin's raw files (imports/garmin/), as saved by scripts/garmin_pull.py.
"""
import datetime as dt, json

import data

STAGES = {0: "deep", 1: "light", 2: "rem", 3: "awake"}


def _garmin_day(day):
    try: return json.loads((data.ROOT / "imports" / "garmin" / day[:4] / f"{day}.json").read_text(encoding="utf-8"))
    except Exception: return {}


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
    p = data.ROOT / "imports" / "garmin" / day[:4] / f"{day}.json"
    try: return p.stat().st_mtime
    except OSError: return None


# ---------- sleep ----------

def sleep_stages(day):
    """The night that ended on the morning of `day`, as [(start, end, stage)] with stage deep/light/rem/awake."""
    out = []
    for x in ((_garmin_day(day).get("sleep") or {}).get("sleepLevels") or []):
        try: out.append((_utc(x["startGMT"]), _utc(x["endGMT"]), STAGES.get(int(x.get("activityLevel", 1)), "light")))
        except Exception: continue
    return out


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
    end = s.get("wellnessEndTimeLocal")
    return {"steps": s.get("totalSteps"), "stress_avg": s.get("averageStressLevel"), "active_kcal": s.get("activeKilocalories"),
            "bmr_kcal": s.get("bmrKilocalories"), "total_kcal": s.get("totalKilocalories"), "synced_to": end[:16] if end else None,
            "body_battery_now": s.get("bodyBatteryMostRecentValue"), "intensity_goal": s.get("intensityMinutesGoal"),
            "last_sync": (s.get("lastSyncTimestampGMT") or "")[:10] or None}


def steps_timeline(day):
    """[(time, steps)] in 15-minute blocks over the day."""
    return [(_utc(t), v) for t, v in _garmin_day(day).get("steps_intraday") or []]


def body_battery_timeline(day):
    """[(time, level)] over the day. Garmin only."""
    return [(_utc(t), v) for t, v in _garmin_day(day).get("body_battery_intraday") or []]


def recent_days(n=7):
    """The newest `n` days that have detail data, newest first."""
    folder = data.ROOT / "imports" / "garmin"
    return [p.stem for p in sorted(folder.glob("[0-9][0-9][0-9][0-9]/*.json"), reverse=True)[:n]]


def fitness_age():
    """{date: {fitnessAge, achievableFitnessAge, ...}} from Garmin, or {}."""
    p = data.ROOT / "imports" / "garmin" / "fitness_age.json"
    try: return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception: return {}


# ---------- workouts ----------

def workout_detail(e):
    """The saved detail for a logged session: {samples: [[epoch ms, hr, ...]], laps: [{distance_m, duration_s, ...}],
    summary: {recoveryHeartRate, activityTrainingLoad, ...}, aerobic_te, anaerobic_te, te_label, body_battery_change};
    None if the session has none."""
    aid = (e or {}).get("garmin_id")
    if not aid: return None
    try: return json.loads((data.ROOT / "imports" / "garmin" / "activities" / f"{aid}.json").read_text(encoding="utf-8"))
    except Exception: return None
