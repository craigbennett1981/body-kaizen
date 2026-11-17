"""Apple Health adapter: samples sent by the Body Kaizen Sync iPhone app -> Body Kaizen records (records.py), and the
detail data behind them (sleep stages, per-minute heart rate, 15-minute steps, workout traces) for app/series.py.

Everything Apple-specific about the shape of the data lives here; the merge into day files is shared by all sources.
See docs/iphone-sync.md, "The translation layer" and "Wire format".

A sample, as the receiver stores it:

    {"uuid": "…", "type": "heart_rate", "start": "2026-11-17T06:10:00+00:00", "end": "…", "tz": "Europe/London",
     "value": 52, "unit": "count/min", "source": {"name": "…", "bundle": "…", "device": "Watch7,3"}, "metadata": {}}

Rules (from the design):
- HRV is SDNN and says so (`hrv_method="sdnn"`), so it never shares a baseline with Garmin's RMSSD.
- Sleep stages map to four: core is light; "asleep, unspecified" counts as asleep with no stage.
- Days follow each sample's own time zone (`tz`, else the offset it was sent with), not this computer's.
- Apple Watch beats iPhone where both measured the same thing; the iPhone fills the time the watch was off.
- Derived numbers: Apple has no heart-rate zones per workout, so ours are computed from its heart rate with the
  Training tab's zone bounds (50/60/70/80/90% of max HR).
"""
import datetime as dt
import statistics
from zoneinfo import ZoneInfo

SOURCE = "apple"

# Our type names (the phone sends these) -> the units each may come in. The receiver refuses any other type before it
# touches anything, since type names end up in table names and log lines.
TYPES = {
    "sleep": {""}, "heart_rate": {"count/min"}, "resting_heart_rate": {"count/min"}, "hrv_sdnn": {"ms"},
    "respiratory_rate": {"count/min"}, "oxygen_saturation": {"%"}, "steps": {"count"}, "active_energy": {"kcal"},
    "basal_energy": {"kcal"}, "workout": {"s"}, "body_mass": {"kg", "lb"}, "body_fat": {"%"},
    "blood_pressure": {"mmHg"}, "vo2max": {"ml/(kg*min)"}, "blood_glucose": {"mmol/L", "mg/dL"},
}
SLEEP_VALUES = {"in_bed", "asleep", "awake", "core", "deep", "rem"}
ASLEEP = {"asleep", "core", "deep", "rem"}
STAGE = {"core": "light", "deep": "deep", "rem": "rem", "awake": "awake", "asleep": "asleep"}
# A plausible range per numeric type: anything outside is a unit mix-up, not a reading, and is skipped.
RANGES = {"heart_rate": (20, 250), "resting_heart_rate": (20, 150), "hrv_sdnn": (1, 400), "respiratory_rate": (3, 60),
          "oxygen_saturation": (50, 100), "steps": (0, 100_000), "active_energy": (0, 20_000), "basal_energy": (0, 20_000),
          "workout": (1, 7 * 86400), "body_mass": (20, 700), "body_fat": (2, 75), "vo2max": (10, 100),
          "blood_glucose": (0.5, 1000)}

# HKWorkoutActivityType case names -> (our type, run mode). Anything else is "other", with Apple's name kept.
ACTIVITY_TYPES = {
    "running": ("run", None), "walking": ("walk", None), "hiking": ("walk", None), "cycling": ("ride", None),
    "swimming": ("swim", None), "traditionalStrengthTraining": ("gym", None), "functionalStrengthTraining": ("gym", None),
    "highIntensityIntervalTraining": ("gym", None), "crossTraining": ("gym", None), "coreTraining": ("gym", None),
    "mixedCardio": ("gym", None), "yoga": ("yoga", None), "pilates": ("yoga", None),
}

ZONE_SHARES = (0.5, 0.6, 0.7, 0.8, 0.9)   # of max HR: the bounds of z1..z5, as the Training tab draws them
NIGHT_GAP = dt.timedelta(hours=2)          # sleep samples further apart than this are separate sleeps
SAMPLE_CAP = 60                            # seconds one heart-rate sample may stand for inside a workout
MG_PER_MMOL = 18.016


# ---------- reading samples ----------

def _parse(ts):
    t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if t.tzinfo is None: raise ValueError(f"time without an offset: {ts!r}")
    return t


def _zone(s):
    try: return ZoneInfo(s["tz"]) if s.get("tz") else None
    except Exception: return None


def when(s, key="start"):
    """A sample's start (or end) as an aware datetime in the time zone it was recorded in."""
    t = _parse(s[key]); z = _zone(s)
    return t.astimezone(z) if z else t


def local_day(s, key="start"):
    return when(s, key).date()


def _utc(t): return t.astimezone(dt.timezone.utc)


def _iso(t): return _utc(t).strftime("%Y-%m-%dT%H:%M:%S")      # series.py reads ISO strings as UTC


def _hhmm(t): return t.strftime("%H:%M")


def device_rank(s):
    """0 for an Apple Watch, 1 for an iPhone, 2 for anything else (another app or device writing into Health)."""
    d = str(((s.get("source") or {}).get("device")) or "").lower()
    return 0 if "watch" in d else 1 if "iphone" in d else 2


def _src(s):
    src = s.get("source") or {}
    return (src.get("bundle") or src.get("name") or "", src.get("device") or "")


def _num(s):
    v = s.get("value")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def valid(s):
    """Why a sample can't be used, or None. The receiver skips (and counts) samples that fail this."""
    typ = s.get("type")
    if typ not in TYPES: return "unknown type"
    if s.get("unit", "") not in TYPES[typ]: return "unexpected unit"
    try:
        a, b = _parse(s["start"]), _parse(s["end"])
    except Exception: return "bad time"
    if b < a: return "ends before it starts"
    if b - a > dt.timedelta(days=2) and typ != "workout": return "too long"
    v = s.get("value")
    if typ == "sleep":
        if v not in SLEEP_VALUES: return "unknown sleep stage"
    elif typ == "blood_pressure":
        if not isinstance(v, dict) or not all(isinstance(v.get(k), (int, float)) and 30 <= v[k] <= 300 for k in ("systolic", "diastolic")):
            return "blood pressure needs systolic and diastolic"
    else:
        n = _num(s)
        if n is None: return "value isn't a number"
        lo, hi = RANGES[typ]
        if typ == "body_mass" and s.get("unit") == "lb": n *= 0.45359237
        if typ == "blood_glucose" and s.get("unit") == "mg/dL": n /= MG_PER_MMOL
        if not lo <= n <= hi: return "value out of range"
    return None


def _of(samples, typ): return [s for s in samples if s.get("type") == typ and valid(s) is None]


def days_touched(s):
    """The local days a sample can change: the day it starts and ends on, and, for anything after noon, the next
    morning's night too (an evening's heart rate or HRV belongs to the night that ends the next day)."""
    a, b = local_day(s), local_day(s, "end")
    out = {a, b}
    if when(s).hour >= 12: out.add(a + dt.timedelta(days=1))
    return out


# ---------- intervals ----------

def _union(iv):
    """[(start, end)] -> merged, non-overlapping, sorted."""
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]: out[-1] = (out[-1][0], max(out[-1][1], b))
        else: out.append((a, b))
    return out


def _secs(iv): return sum((b - a).total_seconds() for a, b in _union(iv))


def _prefer_watch(samples):
    """Of samples measuring the same thing, keep those from the best kind of device present (watch, then iPhone)."""
    if not samples: return []
    best = min(device_rank(s) for s in samples)
    return [s for s in samples if device_rank(s) == best]


def _buckets(samples, minutes):
    """Sum samples into `minutes`-wide slots (by start, UTC). Where a watch and an iPhone both counted a slot, the
    watch's figure is used and the iPhone's dropped; two sources of the same kind are not added up (the larger is
    kept). -> {slot start (UTC): value}"""
    slots = {}
    for s in samples:
        t = _utc(when(s)); t = t.replace(minute=t.minute - t.minute % minutes, second=0, microsecond=0)
        by_src = slots.setdefault(t, {}).setdefault(device_rank(s), {})
        by_src[_src(s)] = by_src.get(_src(s), 0) + _num(s)
    return {t: max(v[min(v)].values()) for t, v in slots.items()}


def _on_day(slots, day, tzs):
    """Slots (UTC) that fall on local `day`, judged in the time zone of the samples."""
    z = tzs or dt.timezone.utc
    return {t: v for t, v in slots.items() if t.astimezone(z).date() == day}


def _tz_of(samples):
    """The time zone most of these samples were recorded in, for placing whole slots on a day."""
    zs = [s["tz"] for s in samples if s.get("tz") and _zone(s)]
    if zs: return ZoneInfo(max(set(zs), key=zs.count))
    if samples: return when(samples[-1]).tzinfo
    return None


# ---------- sleep ----------

def _night(samples, day):
    """The sleep that ended on the morning of `day`: the longest run of sleep samples (gaps under two hours) whose
    end falls on `day`, in the time zone it was recorded in. -> (asleep samples, awake samples) or None."""
    sl = [s for s in _of(samples, "sleep") if s["value"] != "in_bed"]
    if not sl: return None
    sl.sort(key=lambda s: _parse(s["start"]))
    runs, cur, end = [], [], None
    for s in sl:
        a, b = _parse(s["start"]), _parse(s["end"])
        if cur and a - end > NIGHT_GAP: runs.append(cur); cur = []
        cur.append(s); end = b if not cur[:-1] else max(end, b)
    runs.append(cur)
    best, best_s = None, 0
    for r in runs:
        asleep = _prefer_watch([s for s in r if s["value"] in ASLEEP])
        if not asleep: continue
        last = max(asleep, key=lambda s: _parse(s["end"]))
        if local_day(last, "end") != day: continue
        secs = _secs([(_parse(s["start"]), _parse(s["end"])) for s in asleep])
        if secs > best_s: best, best_s = (asleep, _prefer_watch([s for s in r if s["value"] == "awake"])), secs
    return best


def _staged(asleep):
    """Stage intervals for a night: the watch's stages where it has them, else plain "asleep"."""
    staged = [s for s in asleep if s["value"] != "asleep"]
    use = staged if staged else asleep
    return [(_parse(s["start"]), _parse(s["end"]), STAGE[s["value"]]) for s in use]


def _mean(xs, nd=0):
    xs = [x for x in xs if x is not None]
    if not xs: return None
    m = statistics.fmean(xs)
    return round(m) if nd == 0 else round(m, nd)


def night_record(samples, day):
    n = _night(samples, day)
    if not n: return None
    asleep, awake = n
    rec = {"kind": "night", "source": SOURCE}
    iv = [(_parse(s["start"]), _parse(s["end"])) for s in asleep]
    rec["asleep_s"] = round(_secs(iv))
    staged = [s for s in asleep if s["value"] != "asleep"]
    if staged:   # stages only from a device that records them; "asleep, unspecified" adds to the total only
        for v, f in (("deep", "deep_s"), ("core", "light_s"), ("rem", "rem_s")):
            rec[f] = round(_secs([(_parse(s["start"]), _parse(s["end"])) for s in staged if s["value"] == v]))
    a0, b0 = min(iv)[0], max(b for _, b in iv)
    if awake: rec["awake_s"] = round(_secs([(max(a0, _parse(s["start"])), min(b0, _parse(s["end"])))
                                            for s in awake if _parse(s["end"]) > a0 and _parse(s["start"]) < b0]))
    first = min(asleep, key=lambda s: _parse(s["start"])); last = max(asleep, key=lambda s: _parse(s["end"]))
    rec["start"] = when(first).strftime("%Y-%m-%dT%H:%M"); rec["end"] = when(last, "end").strftime("%Y-%m-%dT%H:%M")

    inside = lambda typ, pad=dt.timedelta(0): [s for s in _prefer_watch(_of(samples, typ)) if a0 - pad <= _parse(s["start"]) <= b0 + pad]
    hr = _mean([_num(s) for s in inside("heart_rate")])
    if hr: rec["overnight_hr"] = hr
    hrv = _mean([_num(s) for s in inside("hrv_sdnn", dt.timedelta(minutes=30))])
    if hrv: rec["hrv_ms"] = hrv; rec["hrv_method"] = "sdnn"
    resp = _mean([_num(s) for s in inside("respiratory_rate")], 1)
    if resp: rec["respiration"] = resp
    ox = [_num(s) for s in inside("oxygen_saturation")]
    if ox: rec["spo2_avg"] = _mean(ox); rec["spo2_low"] = round(min(ox))
    return rec


# ---------- the day ----------

def _sum_on(samples, typ, day):
    xs = _of(samples, typ)
    if not xs: return None, {}
    slots = _on_day(_buckets(xs, 15), day, _tz_of(xs))
    return (sum(slots.values()) if slots else None), slots


def day_record(samples, day):
    rec = {"kind": "day", "source": SOURCE}
    steps, _ = _sum_on(samples, "steps", day)
    act, _ = _sum_on(samples, "active_energy", day)
    bmr, _ = _sum_on(samples, "basal_energy", day)
    if steps is not None: rec["steps"] = round(steps)
    if act is not None: rec["energy_active"] = round(act)
    if bmr is not None: rec["energy_bmr"] = round(bmr)
    if act is not None and bmr is not None: rec["energy_total"] = round(act + bmr)
    rhr = sorted((s for s in _prefer_watch([s for s in _of(samples, "resting_heart_rate") if local_day(s) == day])),
                 key=lambda s: _parse(s["start"]))
    if rhr: rec["rhr"] = round(_num(rhr[-1]))
    return rec if len(rec) > 2 else None


# ---------- workouts ----------

def zone_bounds(max_hr):
    return [round(max_hr * f) for f in ZONE_SHARES]


def zones(trace, max_hr, end=None):
    """Seconds in z1..z5 from a heart-rate trace [(time, bpm)]: each reading stands for the time to the next one (at
    most a minute), with the zone bounds the Training tab uses. Below z1 isn't counted."""
    b = zone_bounds(max_hr); out = {}
    for i, (t, hr) in enumerate(trace):
        nxt = trace[i + 1][0] if i + 1 < len(trace) else (end or t)
        secs = min(SAMPLE_CAP, max(0, (nxt - t).total_seconds()))
        z = next((5 - k for k, lo in enumerate(reversed(b)) if hr >= lo), None)
        if z and secs: out[f"z{z}"] = out.get(f"z{z}", 0) + secs
    return {k: round(v) for k, v in sorted(out.items())}


def _trace(samples, a, b):
    hr = [s for s in _prefer_watch(_of(samples, "heart_rate")) if a <= _parse(s["start"]) <= b]
    return sorted(((_parse(s["start"]), _num(s), (s.get("metadata") or {}).get("max")) for s in hr), key=lambda x: x[0])


def _overlap_kcal(samples, typ, a, b):
    """Energy of type `typ` falling inside [a, b], each sample counted in proportion to its overlap."""
    tot, seen = 0.0, False
    for s in _prefer_watch(_of(samples, typ)):
        sa, sb = _parse(s["start"]), _parse(s["end"])
        span = (sb - sa).total_seconds()
        ov = (min(b, sb) - max(a, sa)).total_seconds()
        if ov <= 0: continue
        seen = True; tot += _num(s) * (ov / span if span > 0 else 1)
    return tot if seen else None


def workout_records(samples, day, max_hr=175):
    out = []
    for s in sorted(_of(samples, "workout"), key=lambda s: _parse(s["start"])):
        if local_day(s) != day: continue
        md = s.get("metadata") or {}
        key = str(md.get("activity") or "other")
        typ, mode = ACTIVITY_TYPES.get(key, ("other", None))
        if typ == "run": mode = "treadmill" if md.get("indoor") else "outdoor"
        a, b = _parse(s["start"]), _parse(s["end"])
        w = {"kind": "workout", "source": SOURCE, "type": typ, "source_type": key, "source_id": s["uuid"],
             "start": _hhmm(when(s)), "duration_s": round(_num(s))}
        if mode: w["mode"] = mode
        if isinstance(md.get("distance_m"), (int, float)) and md["distance_m"] > 0: w["distance_m"] = md["distance_m"]
        if typ == "swim" and isinstance(md.get("lap_length_m"), (int, float)) and md["lap_length_m"] > 0: w["pool_m"] = md["lap_length_m"]
        tr = _trace(samples, a, b)
        if tr:
            w["hr_avg"] = round(statistics.fmean(x[1] for x in tr))
            w["hr_max"] = round(max(max(x[1], x[2]) if isinstance(x[2], (int, float)) else x[1] for x in tr))
            z = zones([(t, hr) for t, hr, _ in tr], max_hr, b)
            if z: w["zones_s"] = z
        active = md.get("energy_kcal") if isinstance(md.get("energy_kcal"), (int, float)) else _overlap_kcal(samples, "active_energy", a, b)
        basal = _overlap_kcal(samples, "basal_energy", a, b)
        if active:   # Apple counts a workout's active energy; with the resting part we can show the total as Garmin does
            w["kcal_total"] = round(active + (basal or 0))
            if basal: w["kcal_bmr"] = round(basal)
        if md.get("name"): w["name"] = str(md["name"])[:80]
        out.append(w)
    return out


# ---------- measurements ----------

def measurement_records(samples, day):
    out = []
    for s in sorted((s for s in samples if s.get("type") in ("body_mass", "body_fat", "blood_pressure", "vo2max", "blood_glucose")
                     and valid(s) is None and local_day(s) == day), key=lambda s: _parse(s["start"])):
        m = {"kind": "measurement", "source": SOURCE, "time": _hhmm(when(s))}
        typ, v = s["type"], s["value"]
        if typ == "body_mass": m["weight_kg"] = round(v * (0.45359237 if s["unit"] == "lb" else 1), 2)
        elif typ == "body_fat": m["bf_pct"] = round(v, 1)
        elif typ == "blood_pressure": m["bp_sys"] = round(v["systolic"]); m["bp_dia"] = round(v["diastolic"])
        elif typ == "vo2max": m["vo2max"] = round(v, 1)
        elif typ == "blood_glucose": m["glucose_mmol"] = _mmol(s)
        out.append(m)
    return out


def _mmol(s): return round(s["value"] / MG_PER_MMOL if s["unit"] == "mg/dL" else s["value"], 1)


def records(samples, day, max_hr=175):
    """Every record for local `day` (a date) from the samples: the night that ended that morning, the day, its
    workouts and measurements. `samples` should cover the day before and after too (evening heart rate, a night
    that started the day before). `max_hr` sets the zone bounds for workouts."""
    if isinstance(day, str): day = dt.date.fromisoformat(day)
    out = [r for r in (night_record(samples, day), day_record(samples, day)) if r]
    return out + workout_records(samples, day, max_hr) + measurement_records(samples, day)


# ---------- detail data for app/series.py ----------

def detail(samples, day):
    """What the dashboard draws for `day` beyond the day file, stored in imports/apple/YYYY/YYYY-MM-DD.json and read
    by app/series.py. Times are UTC ISO strings. Holds no sample IDs or device names, only what the charts need:
    {sleep: [[start, end, stage]], steps: [[slot, n]], hr: [[minute, bpm]], glucose: [[time, mmol]],
     workouts: {id: {samples: [[epoch ms, bpm]]}}, extras: {steps, active_kcal, bmr_kcal, total_kcal, synced_to}}"""
    if isinstance(day, str): day = dt.date.fromisoformat(day)
    out = {}
    n = _night(samples, day)
    if n:
        asleep, awake = n
        iv = _staged(asleep) + [(_parse(s["start"]), _parse(s["end"]), "awake") for s in awake]
        out["sleep"] = [[_iso(a), _iso(b), k] for a, b, k in sorted(iv)]
    steps, slots = _sum_on(samples, "steps", day)
    if slots: out["steps"] = [[_iso(t), round(v)] for t, v in sorted(slots.items())]
    hr = _of(samples, "heart_rate")
    if hr:
        z = _tz_of(hr)
        by_min = {}
        for s in hr:
            t = _utc(_parse(s["start"])).replace(second=0, microsecond=0)
            if t.astimezone(z).date() == day: by_min.setdefault(t, []).append(s)
        if by_min: out["hr"] = [[_iso(t), round(statistics.fmean(_num(s) for s in _prefer_watch(v)))] for t, v in sorted(by_min.items())]
    gl = sorted((s for s in _of(samples, "blood_glucose") if local_day(s) == day), key=lambda s: _parse(s["start"]))
    if gl: out["glucose"] = [[_iso(_parse(s["start"])), _mmol(s)] for s in gl]
    wk = {}
    for s in _of(samples, "workout"):
        if local_day(s) != day: continue
        tr = _trace(samples, _parse(s["start"]), _parse(s["end"]))
        if tr: wk[s["uuid"]] = {"samples": [[int(t.timestamp() * 1000), round(v)] for t, v, _ in tr]}
    if wk: out["workouts"] = wk
    act, _ = _sum_on(samples, "active_energy", day)
    bmr, _ = _sum_on(samples, "basal_energy", day)
    ends = [when(s, "end") for s in samples if valid(s) is None and s["type"] in ("steps", "active_energy", "heart_rate")
            and local_day(s, "end") == day]
    ex = {"steps": round(steps) if steps is not None else None, "active_kcal": round(act) if act is not None else None,
          "bmr_kcal": round(bmr) if bmr is not None else None,
          "total_kcal": round(act + bmr) if act is not None and bmr is not None else None,
          "synced_to": max(ends).strftime("%Y-%m-%dT%H:%M") if ends else None}
    if any(v is not None for v in ex.values()): out["extras"] = ex
    return out
