"""Energy balance: today's projected burn and deficit, and the last 30 days' deficit against the weight it should
have moved.

Projected burn for today = Garmin's total at the last watch sync + resting burn for the rest of the day (Garmin's
own resting rate) + the active calories you typically burn after that time of day (median of the last 14 days, from
when your workouts and steps happened). Garmin sends no projection of its own.

Expected weight change = cumulative (burnt - eaten) / 7,700 kcal per kg of body fat. Actual = the trend through your
fasted weigh-ins (least squares, so one salty dinner doesn't swing it). The gap between them, per day, is what your
logging and Garmin's burn estimate disagree by.
"""
import datetime as dt, statistics as stats
import data, daytimeline as T

KCAL_PER_KG = 7700          # energy in a kilo of body fat (the usual rule of thumb; real loss includes some water and lean)
TYPICAL_DAYS = 14
WINDOW = 30
_cache = {}


def _mtime(p):
    try: return p.stat().st_mtime
    except OSError: return None


def _active_curve(day):
    """For a finished day: active (non-resting) calories after each 15-minute mark, from Garmin's active total
    with workouts at their logged times and the rest spread by steps. None if the watch wasn't worn."""
    p = data.day_file(day)
    key = (day, _mtime(p), _mtime(data.ROOT / "imports" / "garmin" / day[:4] / f"{day}.json"))
    if key in _cache: return _cache[key]
    raw = T._raw(day); sm = raw.get("summary") or {}
    steps = [[T._gmt_min(t, day), v] for t, v in raw.get("steps_intraday") or [] if v]
    steps = [s for s in steps if 0 <= s[0] < 1440]
    act, total_steps = sm.get("activeKilocalories"), sum(v for _, v in steps)
    out = None
    if act is not None and total_steps >= 1500:
        bins = [0.0] * 96
        d = data._jsonable(data._load(p)) if p.exists() else {}
        work = 0
        for e in d.get("exercise") or []:
            st = T._hm(e.get("start")); k = (e.get("kcal") or {}).get("active")
            if not st or not k or not e.get("garmin_id"): continue
            s0 = int(st[:2]) * 60 + int(st[3:5]); dur = int(e.get("duration_min") or 45)
            for m in range(s0, min(1440, s0 + dur)): bins[m // 15] += k / dur
            work += k
        rest = max(0, act - work)
        for m, v in steps: bins[m // 15] += rest * v / total_steps
        after, run = [0.0] * 97, 0.0
        for b in range(95, -1, -1):
            run += bins[b]; after[b] = run
        out = after
    _cache[key] = out
    return out


def _typical_active_after(minute, day):
    vals = []
    d0 = dt.date.fromisoformat(day)
    for back in range(1, 45):
        if len(vals) >= TYPICAL_DAYS: break
        c = _active_curve((d0 - dt.timedelta(days=back)).isoformat())
        if c: vals.append(c[min(96, minute // 15)])
    return (round(stats.median(vals)) if vals else None), len(vals)


_factor = {}


def _scale_factor():
    """Real maintenance over Garmin's burn for the same weeks (maintenance.py), or None when there isn't enough data.
    Worked out once per day and data folder: it moves with weeks of data, not with each meal."""
    key = (str(data.ROOT), data.bkenv.now().date().isoformat())
    if key not in _factor: _factor.clear(); _factor[key] = _scale_factor_now()
    return _factor[key]


def _scale_factor_now():
    try:
        import maintenance
        n = (maintenance.build() or {}).get("now") or {}
    except Exception:
        return None
    m, g = n.get("maintenance"), n.get("garmin_burn")
    if not m or not g: return None
    f = m / g
    return f if 0.7 <= f <= 1.3 else None   # outside that the estimate is more likely wrong than Garmin


def today(day=None):
    now = data.bkenv.now()
    day = day or now.date().isoformat()
    raw = T._raw(day); sm = raw.get("summary") or {}
    det = data.day_detail(day) or {}
    eaten = round((det.get("totals") or {}).get("kcal") or 0)
    tgt = (det.get("targets") or {}).get("kcal")
    tmid = round((tgt[0] + tgt[1]) / 2) if isinstance(tgt, (list, tuple)) and len(tgt) == 2 else (tgt if isinstance(tgt, (int, float)) else None)
    if not sm.get("totalKilocalories") or not sm.get("wellnessEndTimeLocal"):
        return {"date": day, "available": False, "eaten": eaten}
    sync = max(0, min(1440, T._iso_to_hm(sm["wellnessEndTimeLocal"], day)))
    so_far = round(sm["totalKilocalories"])
    rate, _ = T._bmr_per_min(day)
    if sync >= 1440 or day < now.date().isoformat():
        projected, rest, active_more, n = so_far, 0, 0, 0
    else:
        rest = round(rate * (1440 - sync))
        active_more, n = _typical_active_after(sync, day)
        projected = so_far + rest + (active_more or 0)
    # Garmin's burn runs high or low for most people: scale it by real maintenance (what you ate and what the scale did)
    # over Garmin's own burn for the same weeks, so the day's figures are in the same kcal as your targets
    adj = _scale_factor(); adj = round(adj, 3) if adj else None
    proj_adj = round(projected * adj) if adj else None
    base = proj_adj if proj_adj is not None else projected
    return {"date": day, "available": True, "scale_factor": adj, "projected_adjusted": proj_adj,
            # the day's balance if you eat exactly your target (middle of the range) from here on
            "deficit_at_target": (base - max(eaten, tmid)) if tmid else None,
            "sync": f"{sync // 60:02d}:{sync % 60:02d}" if sync < 1440 else None,
            "burnt_so_far": so_far, "projected": projected, "rest_of_day_resting": rest, "rest_of_day_active": active_more,
            "typical_days": n, "eaten": eaten, "deficit_so_far": so_far - eaten,
            # the day's deficit if you stop eating now: the projected burn by midnight minus what you've eaten
            "deficit_day": projected - eaten, "target_kcal": tgt, "target_mid": tmid,
            "complete": det.get("status") == "complete"}


def _fit(points):
    """Least-squares line through (day number, kg): (kg per day, kg at day 0). None with fewer than 4 weigh-ins."""
    if len(points) < 4: return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx: return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


def history(days=WINDOW, end=None):
    """The last `days` closed days: burnt (Garmin), eaten, deficit; expected vs actual weight change."""
    S = data.summary()
    today_iso = data.bkenv.today().isoformat()
    end = end or today_iso
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=days)).isoformat()
    rows = []
    for d in S:
        if not (start <= d["date"] < end): continue
        kcal = (d.get("totals") or {}).get("kcal")
        ok = d.get("status") == "complete" and kcal and d.get("burn")
        rows.append({"date": d["date"], "eaten": round(kcal) if kcal else None, "burnt": d.get("burn"),
                     "deficit": round(d["burn"] - kcal) if ok else None})
    counted = [r for r in rows if r["deficit"] is not None]
    avg = round(sum(r["deficit"] for r in counted) / len(counted)) if counted else None
    d0 = dt.date.fromisoformat(start)
    w = [(dt.date.fromisoformat(x["date"]), x["kg"]) for x in data.body()["scale"]
         if x.get("fasted") is not False and start <= x["date"] < end]
    fit = _fit([((dd - d0).days, kg) for dd, kg in w])
    out = {"start": start, "end": end, "days": rows, "counted": len(counted), "avg_deficit": avg,
           "kcal_per_kg": KCAL_PER_KG, "weights": [[dd.isoformat(), kg] for dd, kg in w]}
    if avg is not None:
        out["expected_kg"] = round(-avg * days / KCAL_PER_KG, 2)
    if fit:
        slope, icpt = fit
        out["actual_kg"] = round(slope * days, 2)
        out["trend"] = [[start, round(icpt, 2)], [end, round(icpt + slope * days, 2)]]
        # the expected line starts where the trend starts and follows the running deficit (missing days at the average)
        line, kg = [[start, round(icpt, 2)]], icpt
        for r in rows:
            kg -= (r["deficit"] if r["deficit"] is not None else (avg or 0)) / KCAL_PER_KG
            line.append([r["date"], round(kg, 2)])
        out["expected_line"] = line
        if avg is not None:
            # what the scale says the average daily balance really was, and how far that is from the logs
            out["actual_avg_deficit"] = round(-slope * KCAL_PER_KG)
            out["gap_kcal_day"] = avg - out["actual_avg_deficit"]
    return out


def build(day=None):
    return {"today": today(day), "history": history()}
