"""Intensity minutes, counted the way Garmin counts them (moderate + 2 x vigorous), per week and per month,
against the weekly goal: Garmin's own goal when the watch reports one, else 150 (the WHO minimum for adults).
Also the last few days one by one, against a seventh of the weekly goal."""
import calendar, datetime as dt, json
import data

WEEK_GOAL = 150
FULL_WEEK = 5   # a week with fewer days of watch data is shown, but faded and left out of the trend


def _goal():
    """Garmin's weekly intensity-minutes goal from the newest daily file it saved, else 150."""
    folder = data.ROOT / "imports" / "garmin"
    for p in sorted(folder.glob("[0-9][0-9][0-9][0-9]/*.json"), reverse=True)[:7]:
        try: g = (json.loads(p.read_text(encoding="utf-8")).get("summary") or {}).get("intensityMinutesGoal")
        except Exception: continue
        if g: return int(g), "garmin"
    return WEEK_GOAL, "default"


def daily():
    """{date: (moderate, vigorous)} for every day the watch reported intensity minutes."""
    out = {}
    for p in data.day_files():
        d = data._load(p); im = d.get("intensity_min") or {}
        if im.get("moderate") is not None or im.get("vigorous") is not None:
            out[str(d.get("date"))[:10]] = (int(im.get("moderate") or 0), int(im.get("vigorous") or 0))
    return out


def _period(D, start, end, today):
    days = [start + dt.timedelta(n) for n in range((end - start).days + 1)]
    days = [d for d in days if d <= today]
    got = [D[d.isoformat()] for d in days if d.isoformat() in D]
    mod, vig = sum(a for a, _ in got), sum(b for _, b in got)
    return {"start": start.isoformat(), "end": end.isoformat(), "days": len(days), "days_with_data": len(got),
            "moderate": mod, "vigorous": vig, "total": mod + 2 * vig if got else None, "current": end >= today}


def build(weeks=26, months=None, days=7):
    """Weeks back to `weeks` ago, months back to the first data (or `months`), and the last `days` days one by one."""
    D = daily(); goal, source = _goal(); today = data.bkenv.today()
    out = {"goal": goal, "goal_source": source, "full_week_days": FULL_WEEK, "weeks": [], "months": [], "days": [],
           "trend": None, "this_week": None}
    if not D: return out
    first = dt.date.fromisoformat(min(D))
    if months is None: months = (today.year - first.year) * 12 + today.month - first.month + 1
    for i in range(days - 1, -1, -1):
        d = today - dt.timedelta(days=i)
        if d < first: continue
        x = _period(D, d, d, today); x["goal"] = round(goal / 7); x["partial_data"] = False
        out["days"].append(x)
    monday = today - dt.timedelta(days=today.weekday())
    W = []
    for i in range(weeks - 1, -1, -1):
        s = monday - dt.timedelta(weeks=i)
        if s + dt.timedelta(6) < first: continue
        w = _period(D, s, s + dt.timedelta(6), today)
        w["goal"] = goal; w["partial_data"] = not w["current"] and w["days_with_data"] < FULL_WEEK
        W.append(w)
    M = []
    y, m = today.year, today.month
    for _ in range(months):
        s = dt.date(y, m, 1); e = dt.date(y, m, calendar.monthrange(y, m)[1])
        if e >= first:
            p = _period(D, s, e, today)
            p["goal"] = round(goal * ((e - s).days + 1) / 7)          # the weekly goal, pro rata for the month
            p["goal_so_far"] = round(goal * p["days"] / 7)
            p["partial_data"] = not p["current"] and p["days_with_data"] < p["days"] * FULL_WEEK / 7
            M.append(p)
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    M.reverse()
    full = [w for w in W if not w["current"] and not w["partial_data"]]
    if len(full) >= 2:
        last, prev = full[-4:], full[-8:-4]
        avg = lambda xs: round(sum(w["total"] for w in xs) / len(xs)) if xs else None
        a, b = avg(last), avg(prev)
        chg = round((a - b) / b * 100) if b else None
        out["trend"] = {"avg_4w": a, "avg_prev_4w": b, "weeks_in_avg": len(last), "change_pct": chg,
                        "direction": None if chg is None else "up" if chg >= 10 else "down" if chg <= -10 else "flat",
                        "met": sum(1 for w in full[-12:] if w["total"] >= goal), "of": len(full[-12:])}
    cur = W[-1] if W and W[-1]["current"] else None
    if cur:
        need = max(0, goal - (cur["total"] or 0)); left = 7 - cur["days"]
        out["this_week"] = {"total": cur["total"] or 0, "goal": goal, "days_left": left, "need": need,
                            "per_day": round(need / left) if left and need else 0}
    out["weeks"], out["months"] = W, M
    return out
