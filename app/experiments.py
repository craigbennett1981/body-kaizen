"""The Experiments tab: n-of-1 tests on your own data.

An experiment is a rule you follow for a set number of nights ("asleep by 22:30 for 14 nights"), and the outcomes it
should move (time asleep, sleep score, overnight HRV...). It lives in the data folder's experiments.yaml, written by
your assistant when you say "start the bedtime experiment"; see SCHEMA.md.

Scoring: the nights in the experiment that kept to the rule are compared with every night in the weeks before it
started (the baseline). For each outcome: the difference in averages, and a 90% range for it from resampling those
nights (bootstrap), so a handful of good nights doesn't read as proof. An outcome only counts as better or worse when
the whole range is on one side of zero.

Nights are keyed by the day you wake up, as on the Sleep tab: the rule is checked against that night's bedtime and
the day before it (its training, meals and caffeine), and the outcomes are that night's sleep and the morning's HRV
and resting heart rate.

Suggestions come from the Sleep tab's comparisons: where your own nights already show a pattern, the test that
would settle it.
"""
import datetime as dt, random, statistics as st
import data, sleep

MIN_NIGHTS = 5           # kept nights needed before showing a result
ENOUGH_KEPT = 0.6        # share of nights kept for a finished experiment to count
BASELINE_DAYS = 28
RESAMPLES = 2000


def _hm(v):
    h, m = map(int, str(v)[:5].split(":")); return h * 60 + m


def _night_min(v):
    """'22:30' -> minutes from the wake day's midnight (evening times are negative), as sleep.nights() stores bedtimes."""
    m = _hm(v); return m - 1440 if m >= 12 * 60 else m


# rule key -> (how it reads, test on a night row)
RULES = {
    "bedtime_by": ("Asleep by {v}", lambda r, v: r["start"] <= _night_min(v)),
    "session_end_by": ("Training finished by {v}", lambda r, v: r["before"]["session_end"] is None or r["before"]["session_end"] <= _hm(v)),
    "last_meal_by": ("Last food by {v}", lambda r, v: r["before"]["last_meal"] is None or r["before"]["last_meal"] <= _hm(v)),
    "caffeine_cutoff": ("No caffeine after {v}", lambda r, v: sum(mg for t, mg in r["before"]["caffeine"] if t >= _hm(v)) < 20),
    "sat_fat_max": ("Saturated fat {v} g or less", lambda r, v: r["before"]["satfat"] is not None and r["before"]["satfat"] <= float(v)),
    "steps_min": ("{v} steps or more", lambda r, v: (r["before"]["steps"] or 0) >= float(v)),
}

# outcome key -> (label, unit, row field, +1 if higher is better)
OUTCOMES = {
    "asleep": ("Time asleep", "min", "asleep", +1),
    "sleep_score": ("Sleep score", "", "score", +1),
    "hrv": ("Overnight HRV", "ms", "hrv", +1),
    "rhr": ("Resting heart rate", "bpm", "rhr", -1),
    "deep": ("Deep sleep", "min", "deep", +1),
    "rem": ("REM sleep", "min", "rem", +1),
    "awake": ("Awake in the night", "min", "awake", -1),
}


def rule_text(rule):
    return " and ".join(RULES[k][0].format(v=f"{float(v):,.0f}" if k == "steps_min" else v) for k, v in (rule or {}).items() if k in RULES)


def kept(row, rule):
    return all(RULES[k][1](row, v) for k, v in (rule or {}).items() if k in RULES)


def _boot(a, b, seed=7):
    """90% range for mean(a) - mean(b) by resampling both."""
    rnd = random.Random(seed); diffs = []
    for _ in range(RESAMPLES):
        diffs.append(st.mean(rnd.choices(a, k=len(a))) - st.mean(rnd.choices(b, k=len(b))))
    diffs.sort()
    return diffs[int(.05 * RESAMPLES)], diffs[int(.95 * RESAMPLES) - 1]


def _mh(m):
    return "–" if m is None else f"{int(m) // 60}h {int(m) % 60:02d}m"


def _and(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def compare(trial, base, outcome):
    label, unit, field, sign = OUTCOMES[outcome]
    a = [r[field] for r in trial if r.get(field) is not None]; b = [r[field] for r in base if r.get(field) is not None]
    out = {"key": outcome, "label": label, "unit": unit, "better_if": "higher" if sign > 0 else "lower", "n": len(a), "n_base": len(b),
           "base": round(st.mean(b), 1) if b else None, "trial": round(st.mean(a), 1) if a else None}
    if len(a) < MIN_NIGHTS or len(b) < MIN_NIGHTS:
        out["verdict"] = "too early"; return out
    lo, hi = _boot(a, b)
    out.update(diff=round(st.mean(a) - st.mean(b), 1), lo=round(lo, 1), hi=round(hi, 1))
    good_lo, good_hi = (lo, hi) if sign > 0 else (-hi, -lo)
    out["verdict"] = "better" if good_lo > 0 else "worse" if good_hi < 0 else "unclear"
    return out


def _load():
    f = data.ROOT / "experiments.yaml"
    if not f.exists(): return []
    d = data._jsonable(data._load(f)) or {}
    return [e for e in (d.get("experiments") or []) if isinstance(e, dict) and e.get("start")]


def evaluate(e, rows, today):
    start = dt.date.fromisoformat(str(e["start"])); n = int(e.get("days") or 14)
    first, last = start + dt.timedelta(days=1), start + dt.timedelta(days=n)   # nights keyed by wake day
    rule, outs = e.get("rule") or {}, [o for o in (e.get("outcomes") or ["asleep", "sleep_score", "hrv"]) if o in OUTCOMES]
    bdays = int(e.get("baseline_days") or BASELINE_DAYS)
    base = [r for r in rows if start - dt.timedelta(days=bdays) < dt.date.fromisoformat(r["date"]) <= start]
    inside = [r for r in rows if first <= dt.date.fromisoformat(r["date"]) <= last]
    trial = [r for r in inside if kept(r, rule)]
    nights_so_far = min(n, max(0, (min(today, last) - start).days))
    status = e.get("status") or ("planned" if today <= start else "active" if today < last else "done")
    cal = []
    for i in range(n):
        d = (first + dt.timedelta(days=i)).isoformat(); r = next((x for x in inside if x["date"] == d), None)
        cal.append({"date": d, "state": "future" if dt.date.fromisoformat(d) > today else "no data" if r is None else "kept" if kept(r, rule) else "missed",
                    "bed": sleep._clock(r["start"]) if r else None})
    results = [compare(trial, base, o) for o in outs]
    share = len(trial) / nights_so_far if nights_so_far else None
    if status in ("done", "stopped"):
        if not share or share < ENOUGH_KEPT or len(trial) < MIN_NIGHTS:
            verdict = ("inconclusive", f"Not enough nights kept to the rule ({len(trial)} of {nights_so_far}) to say.")
        else:
            low = lambda t: t[0].lower() + t[1:]   # "Overnight HRV" -> "overnight HRV"
            better = [low(r["label"]) for r in results if r["verdict"] == "better"]; worse = [low(r["label"]) for r in results if r["verdict"] == "worse"]
            verdict = (("worked", "It worked: " + _and(better) + (" improved." if len(better) > 1 else " improved.") + (f" But {_and(worse)} got worse." if worse else ""))
                       if better else ("worse", "It made " + _and(worse) + " worse.") if worse else
                       ("no effect", "No clear effect: any change was within what ordinary night-to-night variation would give."))
    elif status == "active":
        verdict = ("running", f"Night {nights_so_far} of {n}. " + ("Too early to read anything." if len(trial) < MIN_NIGHTS else "Early read: it can still change."))
    else:
        verdict = ("planned", f"Starts the evening of {start:%a %d %b}.".replace(" 0", " "))
    return {"id": e.get("id") or str(e["start"]), "title": e.get("title") or rule_text(rule), "hypothesis": e.get("hypothesis"),
            "rule": rule, "rule_text": rule_text(rule), "start": start.isoformat(), "end": last.isoformat(), "days": n, "status": status,
            "nights_so_far": nights_so_far, "kept": len(trial), "missed": len(inside) - len(trial), "share_kept": round(share, 2) if share is not None else None,
            "baseline": {"from": (start - dt.timedelta(days=bdays - 1)).isoformat(), "to": start.isoformat(), "nights": len(base)},
            "calendar": cal, "results": results, "verdict": verdict[0], "verdict_text": verdict[1], "notes": e.get("notes")}


def _yaml(key, title, rule):
    """The experiments.yaml entry that starts this test tonight."""
    r = ", ".join('%s: "%s"' % (k, v) for k, v in rule.items())
    return ("- id: %s\n  title: %s\n  start: %s\n  days: 14\n  rule: {%s}\n  outcomes: [asleep, sleep_score, hrv]"
            % (key, title, data.bkenv.today().isoformat(), r))


def suggestions(rows, taken):
    """Tests worth running, from patterns already in your nights, best evidence first."""
    out = []
    F = {f["name"]: f for f in sleep.factors(rows)}
    tf = data.ROOT / "targets.yaml"
    target = round((sleep._find(data._jsonable(data._load(tf)) if tf.exists() else {}, "sleep_hours_min") or 7.5) * 60)
    rec = rows[-sleep.RECENT:]; tn = sleep.tonight(rows, target, rec) if rec else None
    def add(key, title, rule, why, hyp, strength, name):
        if key in taken: return
        out.append({"id": key, "name": name, "title": title, "rule": rule, "rule_text": rule_text(rule), "why": why, "hypothesis": hyp, "days": 14,
                    "outcomes": ["asleep", "sleep_score", "hrv"], "strength": strength,
                    "yaml": _yaml(key, title, rule)})
    # bedtime: the lever behind most short nights
    if rows:
        by = "22:30"
        if tn and tn.get("in_bed"):
            m = (_hm(tn["in_bed"]) + 15) % 1440; m = 15 * round(m / 15); by = f"{m // 60:02d}:{m % 60:02d}"
        early = [r for r in rows if r["start"] <= _night_min(by) + 30]; late = [r for r in rows if r["start"] > _night_min(by) + 30]
        if len(early) >= 3 and len(late) >= 3:
            d_sleep = round(st.mean(r["asleep"] for r in early) - st.mean(r["asleep"] for r in late))
            hv = [r["hrv"] for r in early if r["hrv"]], [r["hrv"] for r in late if r["hrv"]]
            d_hrv = round(st.mean(hv[0]) - st.mean(hv[1])) if hv[0] and hv[1] else None
            add("bedtime", f"Asleep by {by}", {"bedtime_by": by},
                f"On your nights asleep by about {sleep._clock(_night_min(by) + 30)} you slept {abs(d_sleep)} min {'more' if d_sleep >= 0 else 'less'}"
                + (f" and HRV was {abs(d_hrv)} ms {'higher' if d_hrv >= 0 else 'lower'}" if d_hrv is not None else "") + f" ({len(early)} vs {len(late)} nights).",
                "An earlier, fixed bedtime gives longer sleep and better recovery.", len(early) + len(late), "bedtime")
    for name, key, rule, hyp, short in (("Late session", "session-by-19", {"session_end_by": "19:00"}, "Finishing training by 19:00 protects that night's sleep.", "late training"),
                                        ("Late last meal", "meal-by-2030", {"last_meal_by": "20:30"}, "An earlier last meal gives better sleep and overnight HRV.", "late meal"),
                                        ("Caffeine after 2 pm", "caffeine-2pm", {"caffeine_cutoff": "14:00"}, "No caffeine after 2 pm helps sleep.", "caffeine")):
        f = F.get(name)
        if not f: continue
        hurt = (f["d_score"] or 0) <= -3 or (f["d_asleep"] or 0) <= -15 or (f["d_hrv"] or 0) <= -4
        if not hurt: continue
        why = (f"Nights after a {f['yes']}: {_mh(f['a']['asleep'])} asleep, score {f['a']['score']}, HRV {f['a']['hrv']} ms, against "
               f"{_mh(f['b']['asleep'])}, {f['b']['score']} and {f['b']['hrv']} ms ({f['a']['n']} vs {f['b']['n']} nights"
               + ("" if f["enough"] else "; few nights, so worth testing properly") + ").")
        add(key, RULES[next(iter(rule))][0].format(v=next(iter(rule.values()))), rule, why, hyp, f["a"]["n"] + f["b"]["n"], short)
    return sorted(out, key=lambda s: -s["strength"])


def build():
    today = data.bkenv.today()
    exps = _load()
    first = min((dt.date.fromisoformat(str(e["start"])) for e in exps), default=today) - dt.timedelta(days=BASELINE_DAYS + 2)
    span = max(sleep.WINDOW, (today - first).days + 2)
    rows = sleep.nights(days=span)
    E = [evaluate(e, rows, today) for e in exps]
    E = [x for x in E if x["status"] in ("active", "planned")] + sorted([x for x in E if x["status"] not in ("active", "planned")], key=lambda x: x["start"], reverse=True)
    taken = {x["id"] for x in E if x["status"] in ("active", "planned")}
    return {"experiments": E, "suggestions": suggestions(rows[-sleep.WINDOW:], taken), "min_nights": MIN_NIGHTS, "enough_kept": ENOUGH_KEPT,
            "rules": {k: v[0] for k, v in RULES.items()}, "outcomes": {k: {"label": v[0], "unit": v[1], "better_if": "higher" if v[3] > 0 else "lower"} for k, v in OUTCOMES.items()}}
