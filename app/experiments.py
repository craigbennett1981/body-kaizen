"""The Experiments tab: n-of-1 tests on your own data.

An experiment is a rule kept for a number of nights (14 unless you say otherwise) and the outcomes it should move.
It lives in the data folder's experiments.yaml, written by your assistant when you say "start the bedtime
experiment"; see SCHEMA.md.

Everything an experiment can mention is in CATALOGUE below, plus foods and supplements from your food list
(food.<key>) and the habits you declare (habit.<name>). Anything else is rejected with a message on the tab, never
silently ignored.

Nights are keyed by the day you wake up, as on the Sleep tab: night.* is that night's sleep and the morning's HRV
and resting heart rate; day.*, food.* and habit.* are the day before it (the evening you went to bed).

Scoring: the nights that kept to the rule are compared with every night in the weeks before it started. For each
outcome, the difference in averages and a 90% range for it from resampling (bootstrap). An outcome only counts as
better or worse when the whole range is on one side of zero.

The tab's "Try a rule" panel runs the same comparison in the browser over the table this module returns, so it
works on the static demo too; static/app.js must split nights the same way.
"""
import datetime as dt, math, random, re, statistics as st
import data, sleep, foods

MIN_NIGHTS = 5           # kept nights needed before showing a result
ENOUGH_KEPT = 0.6        # share of nights kept for a finished experiment to count
BASELINE_DAYS = 28
DEFAULT_DAYS, MIN_DAYS, MAX_DAYS = 14, 3, 60
RESAMPLES = 2000
RAMP_DAYS = 3            # period experiments: days left out at the start while an effect builds
MIN_READINGS = 7         # period experiments: readings needed on each side
PERIOD_KEPT = 0.75       # period experiments: share of days kept for a verdict
TREND_DAYS = 60          # period experiments: days before the start used to check for a trend already under way
BLOCK = 3                # period experiments: resample runs of days, since one day's reading is close to the next
TABLE_NIGHTS = 120       # history sent to the browser for "Try a rule"

# key: (label, kind, unit, group, better)  kind: time (HH:MM), night_time (HH:MM, evening = before midnight),
# num, min (minutes), bool. better: +1 higher is better, -1 lower, 0 depends (say which in the experiment).
# Outcomes: night.* for night experiments; night.*, bp.* and weight.* for period experiments.
CATALOGUE = {
    "night.bedtime": ("Asleep at", "night_time", "", "Night", -1),
    "night.wake": ("Woke at", "time", "", "Night", 0),
    "night.asleep": ("Time asleep", "min", "min", "Night", +1),
    "night.score": ("Sleep score", "num", "", "Night", +1),
    "night.deep": ("Deep sleep", "min", "min", "Night", +1),
    "night.rem": ("REM sleep", "min", "min", "Night", +1),
    "night.awake": ("Awake in the night", "min", "min", "Night", -1),
    "night.hrv": ("Overnight HRV", "num", "ms", "Night", +1),
    "night.rhr": ("Resting heart rate", "num", "bpm", "Night", -1),
    "night.battery": ("Body battery on waking", "num", "", "Night", +1),
    "day.kcal": ("Calories", "num", "kcal", "Food the day before", 0),
    "day.protein": ("Protein", "num", "g", "Food the day before", 0),
    "day.carbs": ("Carbs", "num", "g", "Food the day before", 0),
    "day.fat": ("Fat", "num", "g", "Food the day before", 0),
    "day.satfat": ("Saturated fat", "num", "g", "Food the day before", 0),
    "day.fibre": ("Fibre", "num", "g", "Food the day before", 0),
    "day.sodium": ("Sodium", "num", "mg", "Food the day before", 0),
    "day.caffeine": ("Caffeine", "num", "mg", "Food the day before", 0),
    "day.caffeine_last": ("Last caffeine (20 mg or more)", "time", "", "Food the day before", 0),
    "day.first_meal": ("First food", "time", "", "Food the day before", 0),
    "day.last_meal": ("Last food", "time", "", "Food the day before", 0),
    "day.dinner_kcal": ("Dinner calories", "num", "kcal", "Food the day before", 0),
    "day.dinner_carbs": ("Dinner carbs", "num", "g", "Food the day before", 0),
    "day.trained": ("Trained", "bool", "", "Activity the day before", 0),
    "day.session_end": ("Training finished at", "time", "", "Activity the day before", 0),
    "day.steps": ("Steps", "num", "", "Activity the day before", 0),
    "day.stress": ("Average stress", "num", "", "Activity the day before", 0),
    "bp.morning_sys": ("Morning systolic", "num", "mmHg", "Daily readings", -1),
    "bp.morning_dia": ("Morning diastolic", "num", "mmHg", "Daily readings", -1),
    "bp.morning_pulse": ("Morning pulse", "num", "bpm", "Daily readings", -1),
    "bp.evening_sys": ("Evening systolic", "num", "mmHg", "Daily readings", -1),
    "bp.evening_dia": ("Evening diastolic", "num", "mmHg", "Daily readings", -1),
    "weight.kg": ("Morning weight", "num", "kg", "Daily readings", 0),
}
# a time that didn't happen (no training, no caffeine) keeps "by HH:MM" rules: nothing happened late
ABSENT_KEEPS = {"day.session_end", "day.caffeine_last", "day.last_meal"}
OPS = {"<=", ">=", "<", ">", "=", "!="}
HABIT_KINDS = {"time", "bool", "num", "min"}

# the first rules: kept as shorthand
SHORTHAND = {"bedtime_by": ("night.bedtime", "<="), "session_end_by": ("day.session_end", "<="),
             "last_meal_by": ("day.last_meal", "<="), "caffeine_cutoff": ("day.caffeine_last", "<="),
             "sat_fat_max": ("day.satfat", "<="), "steps_min": ("day.steps", ">=")}
PHRASE = {"night.bedtime": ("Asleep by {v}", "Asleep after {v}"), "day.session_end": ("Training finished by {v}", "Training finished after {v}"),
          "day.last_meal": ("Last food by {v}", "Last food after {v}"), "day.caffeine_last": ("No caffeine after {v}", "Caffeine after {v}"),
          "day.first_meal": ("First food by {v}", "First food after {v}")}


def _hm(v):
    h, m = map(int, str(v)[:5].split(":")); return h * 60 + m


def _mh(m):
    return "–" if m is None else f"{int(m) // 60}h {int(m) % 60:02d}m"


def _and(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


# ---------- the variables you can use ----------

def _amount_unit(f):
    if f.get("liquid"): return "ml"
    if f.get("per100") or f.get("unit_g") or f.get("slice_g") or f.get("default_g"): return "g"
    return "servings"


def catalogue(habits=None):
    """Every variable an experiment may use: the fixed ones, your foods and supplements, your declared habits."""
    n = data._nutrition()
    out = {k: {"label": v[0], "kind": v[1], "unit": v[2], "group": v[3], "better": v[4], "outcome": k.startswith("night."),
               "period_outcome": k.split(".")[0] in ("night", "bp", "weight")} for k, v in CATALOGUE.items()}
    for key, f in n.FOODS.items():
        name = f.get("name") or key.replace("-", " "); grp = "Supplements" if f.get("supplement") else "Foods"
        out["food." + key] = {"label": f"Had {name}", "kind": "bool", "unit": "", "group": grp, "better": 0, "outcome": False,
                              "supplement": bool(f.get("supplement"))}
        out["amount." + key] = {"label": f"Amount of {name}", "kind": "num", "unit": _amount_unit(f), "group": grp, "better": 0,
                                "outcome": False, "supplement": bool(f.get("supplement"))}
    for name, h in (habits or {}).items():
        kind = (h or {}).get("type", "bool") if isinstance(h, dict) else "bool"
        out["habit." + name] = {"label": (h or {}).get("label", name.replace("_", " ")) if isinstance(h, dict) else name.replace("_", " "),
                                "kind": kind if kind in HABIT_KINDS else "bool", "unit": (h or {}).get("unit", "") if isinstance(h, dict) else "",
                                "group": "Your habits", "better": 0, "outcome": False}
    return out


def _value(cat, var, raw):
    """A rule's value in the variable's own terms, or raise ValueError with a message."""
    kind = cat[var]["kind"]
    if kind in ("time", "night_time"):
        if not re.fullmatch(r"\d{1,2}:\d{2}", str(raw)): raise ValueError(f'{var}: "{raw}" isn\'t a time like "22:30"')
        m = _hm(raw); return m - 1440 if kind == "night_time" and m >= 12 * 60 else m
    if kind == "bool":
        if isinstance(raw, bool): return raw
        if str(raw).lower() in ("true", "yes", "1"): return True
        if str(raw).lower() in ("false", "no", "0"): return False
        raise ValueError(f'{var}: "{raw}" should be true or false')
    try: return float(raw)
    except (TypeError, ValueError): raise ValueError(f'{var}: "{raw}" isn\'t a number')


def _conditions(rule):
    """A rule as (combinator, [conditions]); shorthand {bedtime_by: "22:30"} becomes a condition too."""
    if not isinstance(rule, dict): return "all", [], ["rule should be a set of conditions"]
    errs, conds = [], []
    if "all" in rule or "any" in rule:
        comb = "any" if "any" in rule else "all"
        for c in rule.get(comb) or []:
            if isinstance(c, dict) and "var" in c: conds.append({"var": c["var"], "op": str(c.get("op", "=")), "value": c.get("value", True)})
            else: errs.append(f"not a condition: {c!r}")
        extra = set(rule) - {"all", "any"}
        if extra: errs.append(f"unknown keys in rule: {', '.join(sorted(extra))}")
        return comb, conds, errs
    if "var" in rule: return "all", [{"var": rule["var"], "op": str(rule.get("op", "=")), "value": rule.get("value", True)}], errs
    for k, v in rule.items():
        if k in SHORTHAND:
            var, op = SHORTHAND[k]; conds.append({"var": var, "op": op, "value": v})
        else: errs.append(f'unknown rule "{k}"')
    return "all", conds, errs


def check(e, cat):
    """Validate an experiment against the catalogue. Returns (combinator, conditions with parsed values, outcomes, errors)."""
    period = e.get("type") == "period"
    if e.get("type") not in (None, "night", "period"): return "all", [], [], [f'unknown type "{e.get("type")}" (night or period)']
    comb, conds, errs = _conditions((e.get("daily") if period else e.get("rule")) or {})
    if period and e.get("rule"): errs.append("a period experiment's rule goes under daily:, not rule:")
    if not conds and not errs: errs.append("the rule has no conditions")
    for c in conds:
        v = c["var"]
        if v not in cat:
            hint = (" (declare it under habits: in experiments.yaml)" if v.startswith("habit.") else
                    " (it isn't in your food list)" if v.startswith("food.") else "")
            errs.append(f'unknown variable "{v}"{hint}'); continue
        if period and v.split(".")[0] in ("night", "bp", "weight"): errs.append(f"{v} is a result, not something to do each day"); continue
        if c["op"] not in OPS: errs.append(f'{v}: unknown operator "{c["op"]}" (use <=, >=, <, >, = or !=)'); continue
        if cat[v]["kind"] == "bool" and c["op"] not in ("=", "!="): errs.append(f"{v} is yes/no: use = or !="); continue
        try: c["parsed"] = _value(cat, v, c["value"])
        except ValueError as x: errs.append(str(x))
    outs = []
    if period and not e.get("outcomes"): errs.append("a period experiment needs outcomes, e.g. [bp.morning_sys, bp.morning_dia]")
    for o in e.get("outcomes") or ([] if period else ["night.asleep", "night.score", "night.hrv"]):
        better = None
        if isinstance(o, dict): o, better = o.get("var"), o.get("better")
        o = {"asleep": "night.asleep", "sleep_score": "night.score", "hrv": "night.hrv", "rhr": "night.rhr", "deep": "night.deep",
             "rem": "night.rem", "awake": "night.awake"}.get(o, o)   # the first outcome names
        if o not in cat or not (cat[o]["period_outcome"] if period else cat[o]["outcome"]):
            errs.append(f'"{o}" can\'t be an outcome (' + ("night.*, bp.* and weight.* can" if period else "night.* variables can; bp.* and weight.* need type: period") + ")"); continue
        b = {"higher": 1, "lower": -1}.get(better, cat[o]["better"])
        if not b: errs.append(f'{o}: say which way is better, e.g. {{var: {o}, better: lower}}'); continue
        outs.append((o, b))
    if period:
        try:
            if not 0 <= int(e.get("ramp_days", RAMP_DAYS)) < int(e.get("days") or DEFAULT_DAYS) - 3: raise ValueError
        except (TypeError, ValueError): errs.append("ramp_days should be a few days, fewer than the length")
    for r in e.get("requires") or []:
        if r not in REQUIRES and not (str(r).startswith(("habit.", "food.")) and r in cat):
            errs.append(f'unknown requirement "{r}" (use {", ".join(REQUIRES)}, or a habit.* or food.* variable)')
    try: days = int(e.get("days") or DEFAULT_DAYS)
    except (TypeError, ValueError): days = 0
    if not MIN_DAYS <= days <= MAX_DAYS: errs.append(f"days should be {MIN_DAYS} to {MAX_DAYS} (default {DEFAULT_DAYS})")
    try: dt.date.fromisoformat(str(e.get("start")))
    except ValueError: errs.append(f'start "{e.get("start")}" isn\'t a date like 2026-11-08')
    return comb, conds, outs, errs


def _fmt_value(cat, var, c):
    kind = cat[var]["kind"]
    if kind in ("time", "night_time"): return str(c["value"])[:5]
    if kind == "bool": return "yes" if c["parsed"] else "no"
    v = c["parsed"]; s = f"{v:,.0f}" if float(v).is_integer() else f"{v:g}"
    return s + (" " + cat[var]["unit"] if cat[var]["unit"] else "")


def condition_text(cat, c):
    var, op = c["var"], c["op"]
    if var not in cat or "parsed" not in c: return f"{var} {op} {c['value']}"
    meta, val = cat[var], _fmt_value(cat, var, c)
    if var in PHRASE and op in ("<=", "<", ">=", ">"):
        return PHRASE[var][0 if op in ("<=", "<") else 1].format(v=val)
    if meta["kind"] == "bool":
        yes = (op == "=") == bool(c["parsed"])
        lab = meta["label"]
        if var.startswith("food."): return ("Had " if yes else "No ") + lab[4:]
        if var == "day.trained": return "Trained" if yes else "Rest day"
        return (lab[0].upper() + lab[1:]) if yes else "No " + lab
    word = {"<=": "at most", ">=": "at least", "<": "under", ">": "over", "=": "exactly", "!=": "not"}[op]
    if meta["kind"] == "time": word = {"<=": "by", "<": "before", ">=": "at or after", ">": "after", "=": "at", "!=": "not at"}[op]
    return f"{meta['label']} {word} {val}"


def rule_text(cat, comb, conds):
    parts = [condition_text(cat, c) for c in conds]
    parts = [parts[0][0].upper() + parts[0][1:]] + [p[0].lower() + p[1:] for p in parts[1:]] if parts else []
    return (" or " if comb == "any" else " and ").join(parts) if parts else "–"


# ---------- your nights, as a table of the variables ----------

def _day_vars(day, n):
    """The day.*, food.* and habit.* values for one day."""
    out = {}
    try: p = data.day_file(day)
    except ValueError: return out
    if not p.exists(): return out
    f = data._jsonable(data._load(p)) or {}
    t = f.get("totals") or {}
    for k, src in (("kcal", "kcal"), ("protein", "protein_g"), ("carbs", "carbs_g"), ("fat", "fat_g"), ("satfat", "satfat_g"),
                   ("fibre", "fibre_g"), ("sodium", "sodium_mg"), ("caffeine", "caffeine_mg")):
        if t.get(src) is not None: out["day." + k] = t[src]
    times, caf_t, dinner = [], [], {"k": 0.0, "c": 0.0, "any": False}
    for meal, items in (f.get("meals") or {}).items():
        for it in items or []:
            tm = sleep._mins(it.get("time"))
            for c in it.get("parsed") or []:
                key = c.get("item")
                if key not in n.FOODS: continue
                out["food." + key] = True
                amt = foods._amount(c, n.FOODS[key]) if _amount_unit(n.FOODS[key]) != "servings" else c.get("n", 1.0)
                if amt: out["amount." + key] = round(out.get("amount." + key, 0) + amt, 1)
                m = n.macros(c)
                if tm is not None and (m.get("caf") or 0) >= 20: caf_t.append(tm)
                if meal == "dinner": dinner["k"] += m.get("k", 0) or 0; dinner["c"] += m.get("c", 0) or 0; dinner["any"] = True
            if tm is not None and it.get("parsed"): times.append(tm)
    if times: out["day.first_meal"], out["day.last_meal"] = min(times), max(times)
    if caf_t: out["day.caffeine_last"] = max(caf_t)
    if dinner["any"]: out["day.dinner_kcal"], out["day.dinner_carbs"] = round(dinner["k"]), round(dinner["c"], 1)
    ends = []
    for e in f.get("exercise") or []:
        s = sleep._mins(e.get("start"))
        if (e.get("kind") or e.get("type") or "") == "walk": continue
        if s is not None: ends.append(s + int(e.get("duration_min") or 45))
    out["day.trained"] = bool([e for e in f.get("exercise") or [] if (e.get("kind") or e.get("type") or "") != "walk"])
    if ends: out["day.session_end"] = max(ends)
    sm = sleep._raw(day).get("summary") or {}
    if sm.get("totalSteps") is not None or f.get("steps") is not None: out["day.steps"] = sm.get("totalSteps") or f.get("steps")
    if sm.get("averageStressLevel") is not None: out["day.stress"] = sm["averageStressLevel"]
    w = f.get("weight") or {}
    if w.get("kg") and w.get("fasted") is not False: out["weight.kg"] = w["kg"]
    for k, v in (f.get("habits") or {}).items():
        out["habit." + str(k)] = (_hm(v) if isinstance(v, str) and re.fullmatch(r"\d{1,2}:\d{2}", v) else v)
    return out


def table(days):
    """One row per night: night.* from the Sleep tab's nights, the rest from the day before."""
    n = data._nutrition(); rows = []
    for r in sleep.nights(days=days):
        before = (dt.date.fromisoformat(r["date"]) - dt.timedelta(days=1)).isoformat()
        row = {"date": r["date"], "night.bedtime": r["start"], "night.wake": r["end"], "night.asleep": r["asleep"], "night.score": r["score"],
               "night.deep": r["deep"], "night.rem": r["rem"], "night.awake": r["awake"], "night.hrv": r["hrv"], "night.rhr": r["rhr"],
               "night.battery": r["bb"]}
        row.update(_day_vars(before, n)); rows.append(row)
    return rows


def holds(row, c, cat):
    """True / False, or None when the night can't be judged (no value)."""
    v = row.get(c["var"])
    if cat[c["var"]]["kind"] == "bool":
        v = bool(v); return (v == c["parsed"]) if c["op"] == "=" else (v != c["parsed"])
    if v is None:
        return True if (c["var"] in ABSENT_KEEPS and c["op"] in ("<=", "<")) else None
    x = c["parsed"]
    return {"<=": v <= x, ">=": v >= x, "<": v < x, ">": v > x, "=": v == x, "!=": v != x}[c["op"]]


def kept(row, comb, conds, cat):
    res = [holds(row, c, cat) for c in conds]
    if comb == "any": return True if any(r is True for r in res) else None if any(r is None for r in res) else False
    return False if any(r is False for r in res) else None if any(r is None for r in res) else True


# ---------- scoring ----------

def _boot(a, b, seed=7):
    rnd = random.Random(seed); diffs = []
    for _ in range(RESAMPLES):
        diffs.append(st.mean(rnd.choices(a, k=len(a))) - st.mean(rnd.choices(b, k=len(b))))
    diffs.sort()
    return diffs[int(.05 * RESAMPLES)], diffs[int(.95 * RESAMPLES) - 1]


def compare(trial, base, var, sign, cat):
    meta = cat[var]
    a = [r[var] for r in trial if r.get(var) is not None]; b = [r[var] for r in base if r.get(var) is not None]
    unit = "min" if meta["kind"] == "min" else meta["unit"]
    out = {"key": var, "label": meta["label"], "unit": unit, "kind": meta["kind"], "better_if": "higher" if sign > 0 else "lower",
           "n": len(a), "n_base": len(b), "base": round(st.mean(b), 1) if b else None, "trial": round(st.mean(a), 1) if a else None}
    if len(a) < MIN_NIGHTS or len(b) < MIN_NIGHTS:
        out["verdict"] = "too early"; return out
    lo, hi = _boot(a, b)
    out.update(diff=round(st.mean(a) - st.mean(b), 1), lo=round(lo, 1), hi=round(hi, 1))
    good_lo, good_hi = (lo, hi) if sign > 0 else (-hi, -lo)
    out["verdict"] = "better" if good_lo > 0 else "worse" if good_hi < 0 else "unclear"
    return out


def _boot_blocks(a, b, seed=7):
    """90% range for mean(a) - mean(b), resampling runs of BLOCK readings (in date order) from each side."""
    rnd = random.Random(seed)
    def draw(xs):
        if len(xs) <= BLOCK: return st.mean(rnd.choices(xs, k=len(xs)))
        out = []
        while len(out) < len(xs):
            i = rnd.randrange(0, len(xs) - BLOCK + 1); out.extend(xs[i:i + BLOCK])
        return st.mean(out[:len(xs)])
    diffs = sorted(draw(a) - draw(b) for _ in range(RESAMPLES))
    return diffs[int(.05 * RESAMPLES)], diffs[int(.95 * RESAMPLES) - 1]


def daily_table(days):
    """One row per date: the day's food, activity and habits, its morning and evening blood pressure, its weight, and
    the night that ended that morning (night.*). For period experiments and the relationship view."""
    n = data._nutrition(); today = data.bkenv.today()
    nights = {r["date"]: r for r in sleep.nights(days=days)}
    bp = {}
    for b in data.bp_readings():
        if b.get("context") in ("morning", "evening"): bp.setdefault((b["date"], b["context"]), []).append(b)
    rows = []
    for i in range(days - 1, -1, -1):
        d = (today - dt.timedelta(days=i)).isoformat()
        row = {"date": d}; row.update(_day_vars(d, n))
        for ctx in ("morning", "evening"):
            rs = bp.get((d, ctx))
            if rs:
                row[f"bp.{ctx}_sys"] = round(st.mean(r["sys"] for r in rs), 1); row[f"bp.{ctx}_dia"] = round(st.mean(r["dia"] for r in rs), 1)
                ps = [r["pulse"] for r in rs if r.get("pulse")]
                if ctx == "morning" and ps: row["bp.morning_pulse"] = round(st.mean(ps), 1)
        r = nights.get(d)
        if r: row.update({"night.bedtime": r["start"], "night.wake": r["end"], "night.asleep": r["asleep"], "night.score": r["score"],
                          "night.deep": r["deep"], "night.rem": r["rem"], "night.awake": r["awake"], "night.hrv": r["hrv"],
                          "night.rhr": r["rhr"], "night.battery": r["bb"]})
        rows.append(row)
    return rows


def evaluate_period(e, drows, today, cat, comb, conds, outs, base_info):
    """A daily habit kept for a period, judged on the period's readings against the weeks before."""
    start = dt.date.fromisoformat(str(e["start"])); n = int(e.get("days") or DEFAULT_DAYS); ramp = int(e.get("ramp_days", RAMP_DAYS))
    bdays = int(e.get("baseline_days") or BASELINE_DAYS)
    by = {r["date"]: r for r in drows}
    span = [start + dt.timedelta(days=i) for i in range(n)]                 # the days you keep the habit
    judged = [(d, kept(by.get(d.isoformat(), {}), comb, conds, cat) if d < today else "future") for d in span]   # today is still going
    k = sum(1 for _, x in judged if x is True); miss = sum(1 for _, x in judged if x is False)
    so_far = sum(1 for d in span if d <= today)
    status = e.get("status") or ("planned" if today < start else "active" if today < span[-1] + dt.timedelta(days=1) else "done")
    window = [start + dt.timedelta(days=i) for i in range(ramp + 1, n + 1)]   # readings from the morning after the ramp-up on
    base_days = [start - dt.timedelta(days=i) for i in range(bdays - 1, -1, -1)]
    results = []
    for var, sign in outs:
        meta = cat[var]
        a = [by[d.isoformat()][var] for d in window if d <= today and by.get(d.isoformat(), {}).get(var) is not None]
        b = [by[d.isoformat()][var] for d in base_days if by.get(d.isoformat(), {}).get(var) is not None]
        unit = "min" if meta["kind"] == "min" else meta["unit"]
        r = {"key": var, "label": meta["label"], "unit": unit, "kind": meta["kind"], "better_if": "higher" if sign > 0 else "lower",
             "n": len(a), "n_base": len(b), "base": round(st.mean(b), 1) if b else None, "trial": round(st.mean(a), 1) if a else None}
        if len(a) < MIN_READINGS or len(b) < MIN_READINGS: r["verdict"] = "too early"
        else:
            lo, hi = _boot_blocks(a, b); gl, gh = (lo, hi) if sign > 0 else (-hi, -lo)
            diff = st.mean(a) - st.mean(b)
            r.update(diff=round(diff, 1), lo=round(lo, 1), hi=round(hi, 1), verdict="better" if gl > 0 else "worse" if gh < 0 else "unclear")
            # was it already heading this way? the baseline's own trend, carried forward to the middle of the period
            # (fitted over a longer stretch than the baseline: a slope from a few weeks of noisy readings is mostly noise)
            tdays = [start - dt.timedelta(days=i) for i in range(max(bdays, TREND_DAYS), 0, -1)]
            tb = [(d, by[d.isoformat()][var]) for d in tdays if by.get(d.isoformat(), {}).get(var) is not None]
            bx = [(d - start).days for d, _ in tb]; by_ = [v for _, v in tb]
            if len(bx) >= MIN_READINGS and len(set(bx)) > 1:
                mx_, my_ = st.mean(bx), st.mean(by_)
                slope = sum((x - mx_) * (y - my_) for x, y in zip(bx, by_)) / sum((x - mx_) ** 2 for x in bx)
                ax = [(d - start).days for d in window if d <= today and by.get(d.isoformat(), {}).get(var) is not None]
                drift = slope * (st.mean(ax) - mx_)
                if diff and drift * diff > 0 and abs(drift) >= .3 * abs(diff):
                    r["trend"] = round(drift, 1)
                    r["trend_note"] = (f"{meta['label']} was already {'falling' if slope < 0 else 'rising'} before the start: that trend alone would "
                                       f"account for about {abs(drift):.1f} {unit} of the {abs(diff):.1f} {unit} change, so part of it may not be the experiment.")
        results.append(r)
    share = k / (k + miss) if (k + miss) else None
    if status in ("done", "stopped"):
        short = [r for r in results if r["verdict"] == "too early"]
        if not share or share < PERIOD_KEPT:
            verdict = ("inconclusive", f"Not enough days kept ({k} of {k + miss}) to say.")
        elif len(short) == len(results):
            verdict = ("inconclusive", f"Not enough readings to say: it needs {MIN_READINGS}+ in the period and in the weeks before.")
        else:
            low = lambda t: t[0].lower() + t[1:]
            better = [low(r["label"]) for r in results if r["verdict"] == "better"]; worse = [low(r["label"]) for r in results if r["verdict"] == "worse"]
            verdict = (("worked", "It worked: " + _and(better) + " improved." + (f" But {_and(worse)} got worse." if worse else ""))
                       if better else ("worse", "It made " + _and(worse) + " worse.") if worse else
                       ("no effect", "No clear effect: any change was within ordinary day-to-day variation."))
            trends = [r for r in results if r.get("trend_note") and r["verdict"] in ("better", "worse")]
            if trends:
                verdict = ("trend" if verdict[0] in ("worked", "worse") else verdict[0],
                           verdict[1] + " But be careful: " + " ".join(r["trend_note"] for r in trends)
                           )
    elif status == "active":
        verdict = ("running", f"Day {so_far} of {n}." + (f" The first {ramp} days are left out while any effect builds." if so_far <= ramp + 1 else "")
                   + (" Early read: it can still change." if any(r["verdict"] != "too early" for r in results) else " Too early to read anything."))
    else:
        verdict = ("planned", f"Starts {start:%a %d %b}.".replace(" 0", " "))
    cal = [{"date": d.isoformat(), "state": "future" if x == "future" else "kept" if x is True else "missed" if x is False else "no data",
            "ramp": i < ramp, "reading": any(by.get((d + dt.timedelta(days=1)).isoformat(), {}).get(v) is not None for v, _ in outs)}
           for i, (d, x) in enumerate(judged)]
    return {**base_info, "type": "period", "title": e.get("title") or base_info["rule_text"], "start": start.isoformat(),
            "end": span[-1].isoformat(), "days": n, "ramp_days": ramp, "status": status, "nights_so_far": so_far, "kept": k, "missed": miss,
            "share_kept": round(share, 2) if share is not None else None,
            "baseline": {"from": base_days[0].isoformat(), "to": start.isoformat(), "nights": max([r["n_base"] for r in results] or [0]), "unit": "readings"},
            "calendar": cal, "results": results, "verdict": verdict[0], "verdict_text": verdict[1]}


def _load():
    f = data.ROOT / "experiments.yaml"
    if not f.exists(): return [], {}
    d = data._jsonable(data._load(f)) or {}
    return [e for e in (d.get("experiments") or []) if isinstance(e, dict)], (d.get("habits") or {})


def evaluate(e, rows, today, cat, drows=()):
    comb, conds, outs, errs = check(e, cat)
    base_info = {"id": e.get("id") or str(e.get("start")), "title": e.get("title"), "hypothesis": e.get("hypothesis"), "notes": e.get("notes"),
                 "start": str(e.get("start")), "rule_text": rule_text(cat, comb, conds), "errors": errs}
    if errs:
        return {**base_info, "status": "invalid", "verdict": "invalid", "verdict_text": "This experiment can't be scored: " + "; ".join(errs) + ".",
                "days": e.get("days"), "calendar": [], "results": [], "kept": 0, "missed": 0, "nights_so_far": 0}
    if e.get("type") == "period": return evaluate_period(e, drows, today, cat, comb, conds, outs, base_info)
    start = dt.date.fromisoformat(str(e["start"])); n = int(e.get("days") or DEFAULT_DAYS)
    first, last = start + dt.timedelta(days=1), start + dt.timedelta(days=n)
    bdays = int(e.get("baseline_days") or BASELINE_DAYS)
    base = [r for r in rows if start - dt.timedelta(days=bdays) < dt.date.fromisoformat(r["date"]) <= start]
    inside = [r for r in rows if first <= dt.date.fromisoformat(r["date"]) <= last]
    judged = [(r, kept(r, comb, conds, cat)) for r in inside]
    trial = [r for r, k in judged if k is True]; missed = sum(1 for _, k in judged if k is False)
    nights_so_far = min(n, max(0, (min(today, last) - start).days))
    status = e.get("status") or ("planned" if today <= start else "active" if today < last else "done")
    cal = []
    for i in range(n):
        d = (first + dt.timedelta(days=i)).isoformat(); hit = next(((r, k) for r, k in judged if r["date"] == d), None)
        state = "future" if dt.date.fromisoformat(d) > today else "no data" if hit is None or hit[1] is None else "kept" if hit[1] else "missed"
        cal.append({"date": d, "state": state, "bed": sleep._clock(hit[0]["night.bedtime"]) if hit else None})
    results = [compare(trial, base, v, s, cat) for v, s in outs]
    share = len(trial) / (len(trial) + missed) if (len(trial) + missed) else None
    if status in ("done", "stopped"):
        if not share or share < ENOUGH_KEPT or len(trial) < MIN_NIGHTS:
            verdict = ("inconclusive", f"Not enough nights kept to the rule ({len(trial)} of {nights_so_far}) to say.")
        else:
            low = lambda t: t[0].lower() + t[1:]
            better = [low(r["label"]) for r in results if r["verdict"] == "better"]; worse = [low(r["label"]) for r in results if r["verdict"] == "worse"]
            verdict = (("worked", "It worked: " + _and(better) + " improved." + (f" But {_and(worse)} got worse." if worse else ""))
                       if better else ("worse", "It made " + _and(worse) + " worse.") if worse else
                       ("no effect", "No clear effect: any change was within what ordinary night-to-night variation would give."))
    elif status == "active":
        verdict = ("running", f"Night {nights_so_far} of {n}. " + ("Too early to read anything." if len(trial) < MIN_NIGHTS else "Early read: it can still change."))
    else:
        verdict = ("planned", f"Starts the evening of {start:%a %d %b}.".replace(" 0", " "))
    return {**base_info, "title": e.get("title") or base_info["rule_text"], "start": start.isoformat(), "end": last.isoformat(), "days": n,
            "status": status, "nights_so_far": nights_so_far, "kept": len(trial), "missed": missed,
            "share_kept": round(share, 2) if share is not None else None,
            "type": "night", "baseline": {"from": (start - dt.timedelta(days=bdays - 1)).isoformat(), "to": start.isoformat(), "nights": len(base), "unit": "nights"},
            "calendar": cal, "results": results, "verdict": verdict[0], "verdict_text": verdict[1]}


# ---------- what each experiment needs from you today ----------

REQUIRES = {   # readings an experiment can depend on: label, what to do, remind after, the variable that shows it was done
    "bp.morning": ("Morning blood pressure", "Take your morning blood pressure reading.", "10:00", "bp.morning_sys"),
    "bp.evening": ("Evening blood pressure", "Take your evening blood pressure reading.", "21:30", "bp.evening_sys"),
    "weight": ("Morning weigh-in", "Weigh yourself before breakfast.", "10:00", "weight.kg"),
    "sleep": ("Sleep tracked", "Wear your watch overnight and let it sync.", "12:00", "night.asleep"),
}
HABIT_DUE, FOOD_DUE, BED_LEAD = "21:00", "20:00", 45   # when to remind about logging a habit or a food; minutes before a bedtime rule


def _need(var):
    return ("bp.morning" if var.startswith("bp.morning") else "bp.evening" if var.startswith("bp.evening") else
            "weight" if var == "weight.kg" else "sleep" if var.startswith("night.") else None)


def requirements(e, x, row, cat, now_min):
    """Today's checklist for one live experiment: the readings it is judged on (needed during the baseline weeks too)
    and, once it has started, the rule itself. Each item: {key, label, todo, state, due, remind}. state is done, todo,
    on track, missed or tonight; remind means it is due and not done, so worth a toast."""
    if x["status"] not in ("active", "planned"): return []
    comb, conds, outs, errs = check(e, cat)
    if errs: return []
    items = []
    def add(key, label, todo, state, due=None):
        d = _hm(due) if due else None
        items.append({"key": key, "label": label, "todo": todo, "state": state, "due": due,
                      "remind": state in ("todo", "tonight") and d is not None and now_min >= d})
    needs = []
    for v in [o for o, _ in outs] + [c["var"] for c in conds if c["var"].startswith("night.")] + [r for r in (e.get("requires") or []) if r in REQUIRES]:
        n = v if v in REQUIRES else _need(v)
        if n and n not in needs: needs.append(n)
    for n in needs:
        label, todo, due, var = REQUIRES[n]
        add(n, label, todo, "done" if row.get(var) is not None else "todo", due)
    tonight = x["status"] == "planned" and e.get("type") != "period" and str(e.get("start")) == data.bkenv.today().isoformat()
    if x["status"] != "active" and not tonight: return items   # a night experiment's rule starts the evening of its start date
    extra = [{"var": r, "op": "=", "value": True, "parsed": True} for r in (e.get("requires") or []) if str(r).startswith(("habit.", "food."))]
    for c in conds + [c for c in extra if c["var"] not in {k["var"] for k in conds}]:
        v, meta = c["var"], cat[c["var"]]; text = condition_text(cat, c); val = row.get(v)
        if v == "night.bedtime":
            due = (lambda m: f"{m // 60:02d}:{m % 60:02d}")((int(c["parsed"]) - BED_LEAD) % 1440) if c["op"] in ("<=", "<") else None
            if due is not None and now_min >= int(c["parsed"]) % 1440: due = None   # past the time: nothing useful to remind
            add(v, text + " tonight", f"Start winding down now: {text[0].lower() + text[1:]}.", "tonight", due); continue
        if v.startswith("night."): continue
        if v.startswith("habit."):
            shown = (f" (at {int(val) // 60:02d}:{int(val) % 60:02d})" if meta["kind"] == "time" and val is not None else "")
            add(v, f"Log {meta['label'].lower()}" if val is None else text + shown,
                f"Log {meta['label'].lower()} for today ({text[0].lower() + text[1:]}).",
                "todo" if val is None else "done" if holds(row, c, cat) else "missed", HABIT_DUE); continue
        if v.startswith("food.") and c["op"] == "=" and c["parsed"] is True:
            add(v, text, f"{text}, and log it.", "done" if val else "todo", FOOD_DUE); continue
        ok = holds(row, c, cat)
        now_txt = ("" if val is None or meta["kind"] == "bool" else
                   f" (at {int(val) // 60:02d}:{int(val) % 60:02d})" if meta["kind"] in ("time", "night_time") else
                   f" (so far {_fmt_value(cat, v, {'var': v, 'parsed': val, 'value': val})})")
        if c["op"] in ("<=", "<", "!=") or (meta["kind"] == "bool" and c["parsed"] is False):
            state = "missed" if ok is False else "on track"     # a limit: fine until it's broken
        else:
            state = "done" if ok else "todo"
        add(v, text + now_txt, text + ".", state)
    return items


def baseline_progress(x):
    """How the readings before the start are coming along: the fewest of any outcome, against what a verdict needs."""
    ns = [r.get("n_base") for r in x.get("results") or [] if r.get("n_base") is not None]
    if not ns: return None
    return {"have": min(ns), "need": MIN_READINGS if x.get("type") == "period" else MIN_NIGHTS,
            "unit": "readings" if x.get("type") == "period" else "nights"}


def progress(x):
    """For a running experiment: what's left, and how many more misses it can take and still give a verdict."""
    if x["status"] != "active": return None
    left = sum(1 for c in x["calendar"] if c["state"] == "future")
    k, m = x["kept"], x["missed"]; judged = k + m + left
    p = PERIOD_KEPT if x["type"] == "period" else ENOUGH_KEPT
    can = math.floor(k + left - p * judged + 1e-9)
    if x["type"] != "period": can = min(can, k + left - MIN_NIGHTS)
    return {"left": left, "unit": "days" if x["type"] == "period" else "nights", "can_miss": can, "need": p}


NEXT = {   # what to do after a finished experiment, by verdict
    "worked": "Keep the habit. If it matters to you, repeat the experiment in a month or two: a second result is much stronger than one.",
    "worse": "Stop the habit, or change it before trying again.",
    "no effect": "Drop it unless you like it for its own sake, or test a stronger version (an earlier time, a bigger change) for longer.",
    "trend": "Run it again after a steady spell, or stop the habit for two weeks and see if the reading moves back.",
    "inconclusive": "Run it again when you can keep to it most days, and take the readings it needs every day.",
}


def lean(x):
    """Early results are a lean, not a verdict: a range at night 5 is wide and the label can flip."""
    for r in x.get("results") or []:
        if r.get("verdict") in ("better", "worse"): r["lean"] = True


def reminders(B=None):
    """Toasts for the dashboard: requirements that are due today and not yet done."""
    if B is None and not _load()[0]: return []
    B = B or build(); out = []; today = data.bkenv.today()
    for x in B["experiments"]:
        if x["status"] == "active" and x.get("progress"):
            n = x["days"]; half = dt.date.fromisoformat(x["start"]) + dt.timedelta(days=(n + 1) // 2)   # the morning the first half is in
            if 0 <= (today - half).days < 3:
                leans = [f"leaning {r['verdict']} on {r['label'][0].lower() + r['label'][1:]}" for r in x["results"] if r.get("lean")]
                pr = x["progress"]
                out.append({"id": f"exp-{x['id']}-halfway", "since": half.isoformat(), "kind": "remind", "title": f"{x['title']}: halfway",
                            "text": f"Kept {x['kept']} of {x['kept'] + x['missed']} so far, {pr['left']} {pr['unit']} to go"
                                    + (f"; {_and(leans)}." if leans else "; no lean either way yet."),
                            "todo": "Early reads can still flip: keep going." if pr["can_miss"] >= 0 else
                                    "It can't reach enough kept days for a verdict any more: think about stopping it and starting again."})
        if x["status"] == "done" and x.get("finished_on") and 0 <= (today - dt.date.fromisoformat(x["finished_on"])).days < 4:
            out.append({"id": f"exp-{x['id']}-done", "since": x["finished_on"], "kind": "remind", "title": f"{x['title']}: finished",
                        "text": x["verdict_text"].split(" But be careful")[0], "todo": (x.get("next") or "") + " Ask your assistant to write it up."})
        for it in x.get("today") or []:
            if it["remind"]:
                out.append({"id": f"exp-{x['id']}-{it['key']}", "since": data.bkenv.today().isoformat(), "kind": "remind",
                            "title": f"{x['title']}: {it['label'][0].lower() + it['label'][1:]}", "text": it["todo"],
                            "todo": "It's part of an experiment you're running." if x["status"] == "active" else
                                    "Needed for the baseline of an experiment that starts soon."})
    return out


# ---------- suggestions from patterns already in your nights ----------

def _yaml(key, title, conds, days=DEFAULT_DAYS):
    lines = [f"- id: {key}", f"  title: {title}", f"  start: {data.bkenv.today().isoformat()}", f"  days: {days}", "  rule:", "    all:"]
    for c in conds:
        v = c["value"]; v = f'"{v}"' if isinstance(v, str) else ("true" if v is True else "false" if v is False else v)
        lines.append(f'      - {{var: {c["var"]}, op: "{c["op"]}", value: {v}}}')
    lines.append("  outcomes: [night.asleep, night.score, night.hrv]")
    return "\n".join(lines)


def suggestions(nights, taken, cat):
    out = []
    F = {f["name"]: f for f in sleep.factors(nights)}
    tf = data.ROOT / "targets.yaml"
    target = round((sleep._find(data._jsonable(data._load(tf)) if tf.exists() else {}, "sleep_hours_min") or 7.5) * 60)
    rec = nights[-sleep.RECENT:]; tn = sleep.tonight(nights, target, rec) if rec else None

    def add(key, name, conds, why, hyp, strength):
        if key in taken: return
        title = rule_text(cat, "all", [{**c, "parsed": _value(cat, c["var"], c["value"])} for c in conds])
        out.append({"id": key, "name": name, "title": title, "why": why, "hypothesis": hyp, "days": DEFAULT_DAYS, "strength": strength,
                    "rule": {"all": conds}, "yaml": _yaml(key, title, conds)})
    if nights:
        by = "22:30"
        if tn and tn.get("in_bed"):
            m = (_hm(tn["in_bed"]) + 15) % 1440; m = 15 * round(m / 15); by = f"{m // 60:02d}:{m % 60:02d}"
        cut = _value(cat, "night.bedtime", by) + 30
        early = [r for r in nights if r["start"] <= cut]; late = [r for r in nights if r["start"] > cut]
        if len(early) >= 3 and len(late) >= 3:
            d_sleep = round(st.mean(r["asleep"] for r in early) - st.mean(r["asleep"] for r in late))
            hv = [r["hrv"] for r in early if r["hrv"]], [r["hrv"] for r in late if r["hrv"]]
            d_hrv = round(st.mean(hv[0]) - st.mean(hv[1])) if hv[0] and hv[1] else None
            add("bedtime", "bedtime", [{"var": "night.bedtime", "op": "<=", "value": by}],
                f"On your nights asleep by about {sleep._clock(cut)} you slept {abs(d_sleep)} min {'more' if d_sleep >= 0 else 'less'}"
                + (f" and HRV was {abs(d_hrv)} ms {'higher' if d_hrv >= 0 else 'lower'}" if d_hrv is not None else "") + f" ({len(early)} vs {len(late)} nights).",
                "An earlier, fixed bedtime gives longer sleep and better recovery.", len(early) + len(late))
    for fname, key, cond, hyp, short in (
            ("Late session", "session-by-19", {"var": "day.session_end", "op": "<=", "value": "19:00"}, "Finishing training by 19:00 protects that night's sleep.", "late training"),
            ("Late last meal", "meal-by-2030", {"var": "day.last_meal", "op": "<=", "value": "20:30"}, "An earlier last meal gives better sleep and overnight HRV.", "late meal"),
            ("Caffeine after 2 pm", "caffeine-2pm", {"var": "day.caffeine_last", "op": "<=", "value": "14:00"}, "No caffeine after 2 pm helps sleep.", "caffeine")):
        f = F.get(fname)
        if not f: continue
        if not ((f["d_score"] or 0) <= -3 or (f["d_asleep"] or 0) <= -15 or (f["d_hrv"] or 0) <= -4): continue
        why = (f"Nights after a {f['yes']}: {_mh(f['a']['asleep'])} asleep, score {f['a']['score']}, HRV {f['a']['hrv']} ms, against "
               f"{_mh(f['b']['asleep'])}, {f['b']['score']} and {f['b']['hrv']} ms ({f['a']['n']} vs {f['b']['n']} nights"
               + ("" if f["enough"] else "; few nights, so worth testing properly") + ").")
        add(key, short, [cond], why, hyp, f["a"]["n"] + f["b"]["n"])
    return sorted(out, key=lambda s: -s["strength"])


def build():
    today = data.bkenv.today()
    exps, habits = _load()
    cat = catalogue(habits)
    starts = []
    for e in exps:
        try: starts.append(dt.date.fromisoformat(str(e.get("start"))))
        except ValueError: pass
    first = min(starts, default=today) - dt.timedelta(days=max(BASELINE_DAYS, TREND_DAYS) + 2)
    span = max(TABLE_NIGHTS, (today - first).days + 2)
    rows = table(span)
    drows = daily_table(span)
    E = [evaluate(e, rows, today, cat, drows) for e in exps]
    now = data.bkenv.now(); now_min = now.hour * 60 + now.minute
    trow = next((r for r in drows if r["date"] == today.isoformat()), {})
    for e, x in zip(exps, E):
        x["today"] = requirements(e, x, trow, cat, now_min)
        if x["status"] in ("active", "planned"): x["baseline_progress"] = baseline_progress(x)
        x["progress"] = progress(x)
        if x["status"] == "active": lean(x)
        if x["status"] in ("done", "stopped"):
            x["next"] = NEXT.get(x["verdict"])
            if x["status"] == "done":   # a night experiment's last night ends the morning of `end`; a period's last day ends that evening
                x["finished_on"] = (dt.date.fromisoformat(x["end"]) + dt.timedelta(days=1 if x["type"] == "period" else 0)).isoformat()
    live = [x for x in E if x["status"] in ("active", "planned", "invalid")]
    past = sorted([x for x in E if x not in live], key=lambda x: x["start"], reverse=True)
    taken = {x["id"] for x in live}
    nights = sleep.nights(days=sleep.WINDOW)
    # the browser only needs the variables that have any values, plus the date
    recent = rows[-TABLE_NIGHTS:]
    return {"experiments": live + past, "suggestions": suggestions(nights, taken, cat),
            "catalogue": cat, "habits": habits, "ops": sorted(OPS), "min_nights": MIN_NIGHTS, "enough_kept": ENOUGH_KEPT,
            "baseline_days": BASELINE_DAYS, "default_days": DEFAULT_DAYS, "absent_keeps": sorted(ABSENT_KEEPS),
            "table": _cols(recent, cat),
            "daily": _cols(drows[-TABLE_NIGHTS:], cat), "ramp_days": RAMP_DAYS, "min_readings": MIN_READINGS}


def _cols(rows, cat):
    """Columns for the browser. A mostly empty column (most foods) is sent as {"s": [[row, value], ...]}."""
    used = sorted({k for r in rows for k, v in r.items() if k != "date" and v is not None and k in cat})
    out = {}
    for k in used:
        col = [r.get(k) for r in rows]; filled = [[i, v] for i, v in enumerate(col) if v is not None]
        out[k] = {"s": filled} if len(filled) < len(col) * .4 else col
    return {"dates": [r["date"] for r in rows], "cols": out}
