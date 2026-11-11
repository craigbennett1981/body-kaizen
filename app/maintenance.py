"""Your real maintenance calories, worked out from what you ate and what the scale did, not from Garmin's burn.

Maintenance = average intake on closed days - (weight trend, kg per day) x 7,700 kcal per kg. Over 28 days a steady
trend is mostly fat and lean, not water, so the gap between eating and maintenance shows up on the scale. The 90%
range comes from how tightly the weigh-ins follow the trend line.

From that: intake targets shifted so a typical week averages maintenance plus your goal rate (targets.yaml
`adaptive.goal_kg_per_week`; when it isn't set, maintenance and two rates towards your weight target), and where the weight trend lands at the next InBody scan
(`adaptive.next_scan`, else the last scan plus your usual gap between scans) at three ways of eating.
"""
import datetime as dt, math, statistics as stats
import data

KCAL_PER_KG = 7700
WINDOW = 28          # days in each estimate
MIN_DAYS = 14        # closed days with logged food needed for an estimate
MIN_WEIGHS = 6        # fasted weigh-ins needed for a trend (fewer widen the range rather than block it)
WEEKS = 8            # past estimates shown, one per week
Z90 = 1.645
DAY_TYPES = ("rest", "training", "big")


def _fit(points):
    """Least squares through (day, kg): slope, intercept and the slope's standard error. None with too few points."""
    n = len(points)
    if n < 3: return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx: return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(resid / (n - 2) / sxx) if n > 2 else None
    return b, a, se


def _settings():
    return data._targets_file().get("adaptive") or {}


def estimate(S, scale, end, days=WINDOW):
    """Maintenance from the `days` before `end` (ISO date, not included)."""
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=days)).isoformat()
    rows = [d for d in S if start <= d["date"] < end]
    eaten = [d for d in rows if d.get("status") == "complete" and (d.get("totals") or {}).get("kcal")]
    burns = [d["burn"] for d in eaten if d.get("burn")]
    d0 = dt.date.fromisoformat(start)
    w = [((dt.date.fromisoformat(x["date"]) - d0).days, x["kg"]) for x in scale
         if x.get("fasted") is not False and start <= x["date"] < end]
    out = {"start": start, "end": end, "days": days, "logged_days": len(eaten), "weigh_ins": len(w)}
    if len(eaten) < MIN_DAYS or len(w) < MIN_WEIGHS:
        out["needs"] = (f"{MIN_DAYS} closed days of food" if len(eaten) < MIN_DAYS else "") + \
                       (" and " if len(eaten) < MIN_DAYS and len(w) < MIN_WEIGHS else "") + \
                       (f"{MIN_WEIGHS} fasted weigh-ins" if len(w) < MIN_WEIGHS else "")
        return out
    fit = _fit(w)
    if not fit:
        out["needs"] = "weigh-ins on more than one day"; return out
    slope, icpt, se = fit
    intake = sum(d["totals"]["kcal"] for d in eaten) / len(eaten)
    m = intake - slope * KCAL_PER_KG
    half = Z90 * se * KCAL_PER_KG if se is not None else None
    out.update({"intake": round(intake), "maintenance": int(round(m, -1)),
                "low": int(round(m - half, -1)) if half is not None else None,
                "high": int(round(m + half, -1)) if half is not None else None,
                "kg_per_week": round(slope * 7, 2), "balance": round(intake - m),   # + surplus, - deficit
                "trend_kg_end": round(icpt + slope * days, 2), "slope": slope, "slope_se": se})
    if len(burns) >= MIN_DAYS // 2:
        g = sum(burns) / len(burns)
        out["garmin_burn"] = round(g); out["garmin_gap"] = round(g - m)   # + Garmin says you burn more than you do
    return out


def _mid(r):
    return (r[0] + r[1]) / 2 if isinstance(r, (list, tuple)) and len(r) == 2 else r if isinstance(r, (int, float)) else None


def suggest(S, today, maint, goals):
    """Current targets per day type, the share of each day type lately, and for each goal rate (kg a week) the same
    targets shifted so a typical week averages maintenance + that rate (shifts rounded to 25 kcal)."""
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=WINDOW)).isoformat()
    recent = [d["day_type"] for d in S if start <= d["date"] < today]
    mix = {t: (recent.count(t) / len(recent) if recent else (1 if t == "rest" else 0)) for t in DAY_TYPES}
    cur = {}
    for t in DAY_TYPES:
        k = data.targets_for(today, t).get("kcal")
        if k is not None: cur[t] = list(k) if isinstance(k, (list, tuple)) else [k, k]
    if not cur: return None
    tot = sum(mix[t] for t in cur) or 1
    avg_now = sum(_mid(cur[t]) * mix[t] for t in cur) / tot
    opts = []
    for g in goals:
        want = maint + g * KCAL_PER_KG / 7
        shift = int(round((want - avg_now) / 25) * 25)
        opts.append({"goal_kg_per_week": g, "goal_avg": round(want), "shift": shift,
                     "suggested": {t: [r[0] + shift, r[1] + shift] for t, r in cur.items()}})
    return {"mix": {t: round(v, 2) for t, v in mix.items()}, "current": cur, "current_avg": round(avg_now),
            "label": data.targets_for(today, "rest").get("label"), "options": opts}


def floor():
    """The lowest weekly average worth suggesting: your BMR from the latest InBody scan, else the usual minimums
    (1,500 kcal for men, 1,200 otherwise)."""
    try:
        scans = sorted((x for x in data.body()["inbody"] if x.get("bmr_kcal")), key=lambda x: str(x["date"]))
        if scans: return int(scans[-1]["bmr_kcal"]), "InBody BMR"
    except Exception: pass
    try: sex = str((data._load(data.ROOT / "athlete.yaml") or {}).get("sex") or "").lower()
    except Exception: sex = ""
    return (1500 if sex == "male" else 1200), "usual minimum"


def goals(trend_kg, target_kg):
    """The goal rates to offer: yours from targets.yaml (adaptive.goal_kg_per_week), else maintenance plus a gentle
    and a steady rate towards your weight target when the trend is more than half a kilo away from it."""
    g = _settings().get("goal_kg_per_week")
    if g is not None: return [float(g)], True
    if target_kg is None or abs(trend_kg - target_kg) <= 0.5: return [0.0], False
    s = -1 if target_kg < trend_kg else 1
    return [0.0, 0.25 * s, 0.5 * s], False


def next_scan(today):
    """The next InBody date: targets.yaml adaptive.next_scan, else the last scan + the median gap between scans."""
    s = _settings().get("next_scan")
    if s: return str(s)[:10], "planned"
    try: scans = sorted({str(x["date"])[:10] for x in data.body()["inbody"] if x.get("date")})
    except Exception: return None, None
    if len(scans) < 2: return None, None
    ds = [dt.date.fromisoformat(x) for x in scans]
    gap = stats.median((b - a).days for a, b in zip(ds, ds[1:]))
    nxt = ds[-1] + dt.timedelta(days=int(gap))
    t = dt.date.fromisoformat(today)
    while nxt <= t: nxt += dt.timedelta(days=int(gap))
    return nxt.isoformat(), "usual gap"


def build(end=None):
    S = data.summary()
    scale = data.body()["scale"]
    today = end or data.bkenv.today().isoformat()
    now = estimate(S, scale, today)
    t0 = dt.date.fromisoformat(today)
    weeks = []
    for k in range(WEEKS - 1, -1, -1):
        e = estimate(S, scale, (t0 - dt.timedelta(days=7 * k)).isoformat())
        weeks.append({x: e.get(x) for x in ("end", "maintenance", "low", "high", "garmin_burn", "intake")})
    out = {"window": WINDOW, "min_days": MIN_DAYS, "min_weigh_ins": MIN_WEIGHS, "kcal_per_kg": KCAL_PER_KG,
           "now": {k: v for k, v in now.items() if k not in ("slope", "slope_se")}, "weeks": weeks}
    if now.get("maintenance") is None: return out
    G, chosen = goals(now["trend_kg_end"], data.weight_target_for(today))
    sg = suggest(S, today, now["maintenance"], G)
    if sg:
        fl, why = floor()
        sg.update({"chosen": chosen, "floor": fl, "floor_source": why,
                   "dropped": [o["goal_kg_per_week"] for o in sg["options"] if o["goal_avg"] < fl]})
        sg["options"] = [o for o in sg["options"] if o["goal_avg"] >= fl]
    out["targets"] = sg
    scan, how = next_scan(today)
    if scan and scan > today:
        n = (dt.date.fromisoformat(scan) - t0).days
        w0, slope, se = now["trend_kg_end"], now["slope"], now["slope_se"]
        at = lambda avg: round(w0 + (avg - now["maintenance"]) / KCAL_PER_KG * n, 1)
        P = {"date": scan, "source": how, "days": n, "trend_today": w0,
             "as_now": round(w0 + slope * n, 1),
             "as_now_range": [round(w0 + (slope - Z90 * se) * n, 1), round(w0 + (slope + Z90 * se) * n, 1)] if se is not None else None}
        if sg:
            P["at_targets"] = at(sg["current_avg"])
            for o in sg["options"]: o["at_scan"] = at(sg["current_avg"] + o["shift"])
        out["projection"] = P
    return out
