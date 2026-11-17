"""Garmin adapter: raw Garmin Connect JSON (as saved by garmin_pull.py) -> Body Kaizen records (records.py).

Everything Garmin-specific about the shape of its data lives here; the merge into day files is shared by all sources.
"""
import datetime as dt

import bkenv

ACTIVITY_TYPES = {  # Garmin typeKey -> (our type, run mode)
    "running": ("run", "outdoor"), "street_running": ("run", "outdoor"), "track_running": ("run", "outdoor"),
    "treadmill_running": ("run", "treadmill"), "trail_running": ("run", "trail"), "indoor_running": ("run", "treadmill"),
    "strength_training": ("gym", None), "indoor_cardio": ("gym", None), "hiit": ("gym", None),
    "lap_swimming": ("swim", None), "open_water_swimming": ("swim", None), "swimming": ("swim", None),
    "yoga": ("yoga", None), "pilates": ("yoga", None),
    "walking": ("walk", None), "casual_walking": ("walk", None), "speed_walking": ("walk", None), "hiking": ("walk", None),
}


def _put(d, k, v):
    if v is not None: d[k] = v


def _local(ms_gmt):
    """Garmin's GMT milliseconds -> local 'YYYY-MM-DDTHH:MM' (the GMT fields: Garmin's local ones double-shift for UTC+8)."""
    return dt.datetime.fromtimestamp(ms_gmt / 1000, tz=dt.timezone.utc).astimezone(bkenv.tz()).strftime("%Y-%m-%dT%H:%M")


def records(raw):
    """raw = {"summary":..., "sleep":..., "hrv":..., "activities":[...]} -> [night?, day?, workout...]"""
    out = []
    s = raw.get("summary") or {}
    sleep = raw.get("sleep") or {}
    sl = sleep.get("dailySleepDTO") or {}
    hv = (raw.get("hrv") or {}).get("hrvSummary") or {}

    day = {"kind": "day", "source": "garmin"}
    _put(day, "steps", s.get("totalSteps"))
    _put(day, "energy_total", s.get("totalKilocalories")); _put(day, "energy_active", s.get("activeKilocalories"))
    _put(day, "energy_bmr", s.get("bmrKilocalories"))
    _put(day, "intensity_moderate_min", s.get("moderateIntensityMinutes")); _put(day, "intensity_vigorous_min", s.get("vigorousIntensityMinutes"))
    _put(day, "rhr", s.get("restingHeartRate") or sleep.get("restingHeartRate"))
    _put(day, "body_battery", s.get("bodyBatteryChargedValue"))
    _put(day, "stress_avg", s.get("averageStressLevel") if (s.get("averageStressLevel") or -1) >= 0 else None)
    if len(day) > 2: out.append(day)

    night = {"kind": "night", "source": "garmin"}
    if sl.get("sleepTimeSeconds"):
        night["asleep_s"] = sl["sleepTimeSeconds"]
        for k, name in (("deepSleepSeconds", "deep_s"), ("lightSleepSeconds", "light_s"), ("remSleepSeconds", "rem_s"), ("awakeSleepSeconds", "awake_s")):
            _put(night, name, sl.get(k))
        if sl.get("sleepStartTimestampGMT") and sl.get("sleepEndTimestampGMT"):
            night["start"] = _local(sl["sleepStartTimestampGMT"]); night["end"] = _local(sl["sleepEndTimestampGMT"])
    _put(night, "score", ((sl.get("sleepScores") or {}).get("overall") or {}).get("value"))
    _put(night, "spo2_avg", sl.get("averageSpO2Value")); _put(night, "spo2_low", sl.get("lowestSpO2Value"))
    _put(night, "respiration", sl.get("averageRespirationValue"))
    _put(night, "overnight_hr", sl.get("avgHeartRate") or sl.get("averageHeartRate"))
    if hv.get("lastNightAvg") is not None:
        night["hrv_ms"] = hv["lastNightAvg"]; night["hrv_method"] = "rmssd"
    _put(night, "hrv_7d_ms", hv.get("weeklyAvg"))
    if hv.get("status"): night["hrv_status"] = str(hv["status"]).lower()
    if len(night) > 2: out.append(night)

    for a in raw.get("activities") or []:
        key = ((a.get("activityType") or {}).get("typeKey") or "other").lower()
        typ, mode = ACTIVITY_TYPES.get(key, ("other", None))
        name = a.get("activityName") or ""
        if typ == "walk" and "ruck" in name.lower(): typ = "ruck"
        w = {"kind": "workout", "source": "garmin", "type": typ, "source_type": key}
        _put(w, "source_id", a.get("activityId"))
        _put(w, "mode", mode)
        if a.get("startTimeLocal"): w["start"] = str(a["startTimeLocal"])[11:16]
        if a.get("duration"): w["duration_s"] = a["duration"]
        if a.get("movingDuration"): w["moving_s"] = a["movingDuration"]
        if a.get("distance"): w["distance_m"] = a["distance"]
        if a.get("poolLength"): w["pool_m"] = a["poolLength"]
        if a.get("averageHR"): w["hr_avg"] = a["averageHR"]
        if a.get("maxHR"): w["hr_max"] = a["maxHR"]
        if a.get("calories"): w["kcal_total"] = a["calories"]
        if a.get("bmrCalories"): w["kcal_bmr"] = a["bmrCalories"]
        if a.get("averageRunningCadenceInStepsPerMinute"): w["cadence"] = a["averageRunningCadenceInStepsPerMinute"]
        zones = {f"z{i}": a[f"hrTimeInZone_{i}"] for i in range(1, 6) if a.get(f"hrTimeInZone_{i}")}
        if zones: w["zones_s"] = zones
        if name: w["name"] = name
        out.append(w)
    return out
