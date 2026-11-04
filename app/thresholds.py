"""Every threshold the dashboard judges your data against, with where it lives and where it comes from.

Two kinds:
- Rules fixed in the code (RULES below). Edit them here and in docs/thresholds.md together.
- Your own targets and bands from the data folder (targets.yaml, markers.yaml, athlete.yaml,
  exercises.yaml), read live so the page always shows what is actually in force.

"Basis" says where a number comes from: a named guideline when the code relies on one, "heuristic" when it
is a hand-set judgement, "no source" when nothing better can honestly be said.
"""
import datetime as dt
import data, healthscore

# (section, [(threshold, rule, defined in, shown on, basis)])
RULES = [
    ("Food and the day's macros", [
        ("Day judged", "Each target is ticked or crossed only once the day is closed (status complete); "
         "before that you see over/under arrows", "data.py evaluate", "Day, Trends, Week", "design rule"),
        ("Live colour", "Inside the target = green; missed by up to 10% = amber; more = red", "app.js liveStatus",
         "Day macro tiles", "heuristic"),
        ("High sat-fat food", "A single food item with 3 g or more saturated fat is tinted red", "app.js SF_HIGH",
         "Day timeline", "heuristic"),
        ("Guessed portions", "A note when 15% or more of the day's calories come from low-confidence estimates",
         "insights.py", "Day notes", "heuristic"),
        ("Protein spread", "Counts feeds of 30 g protein or more; suggests four of 35–40 g when the target is 150 g+",
         "insights.py", "Day notes", "muscle protein synthesis research (inferred); heuristic"),
        ("Under-eating week", "Under the calorie floor on 60%+ of the last 7 closed days (needs 4+)", "insights.py",
         "Day notes", "heuristic"),
    ]),
    ("Pace through the day", [
        ("Floors and ranges", "Eaten ÷ expected-so-far: 85%+ green, 65–85% amber, below red "
         "(the 85% and 65% come from targets.yaml pace)", "pace.py", "Day pace strips", "heuristic"),
        ("Caps (saturated fat)", "Up to 105% of the allowance so far green, up to 125% amber, above red; over the "
         "full-day cap is always red", "pace.py", "Day pace strips", "heuristic"),
        ("Range ceiling", "More than 115% of the upper end so far = amber (red once over the full-day upper)",
         "pace.py", "Day pace strips", "heuristic"),
        ("Next move", "Sat-fat warning when under 8 g is left; protein prompt when 5 g+ is still needed; "
         "fibre prompt after 12:00 when 5 g+ short", "glance.py", "Day 'next move' line", "heuristic"),
    ]),
    ("Blood pressure", [
        ("Category", "Normal under 120/80; elevated 120–129 systolic; stage 1 130–139 or 80–89; "
         "stage 2 140+ or 90+; crisis 180+ or 120+", "data.py bp_category", "Body, Day notes, Doctor page",
         "2017 ACC/AHA adult guideline"),
        ("Morning reading", "Before the time in settings.yaml (vitals.bp.morning_before, default 09:00)",
         "data.py", "Body (30-day morning average)", "measurement practice: same time, before coffee"),
        ("Pulse pressure", "Systolic − diastolic: under 30 narrow; 30–50 healthy; 50–60 upper normal; "
         "over 60 wide, worth watching", "app.js ppCat", "Body", "40 typical and 60+ linked with artery stiffness "
         "in cohort studies (common rule of thumb); 30 and 50 cut-offs are heuristic"),
    ]),
    ("Glucose (CGM)", [
        ("In range", "3.9–7.8 mmol/L", "glucose.py LOW, HIGH", "Day glucose panel, Body",
         "non-diabetic 'tight range' (inferred); the 2019 International Consensus 3.9–10.0 range is for diabetes"),
        ("Sensor settling", "First 24 h of each sensor left out of rolling figures", "glucose.py SETTLE_H",
         "Body", "first-day sensor accuracy is lower (manufacturer guidance, inferred)"),
        ("Time in range chip", "95%+ green, under 85% red", "app.js", "Day, Body", "mirrors the cgm_tir marker"),
        ("Variability chip", "CV 18% or less green, over 25% red", "app.js", "Day", "mirrors the cgm_cv marker"),
        ("Meal response", "Baseline = mean of the 30 min before; rise measured over 150 min; rise of 3.0+ red, "
         "1.5 or less green", "glucose.py, app.js", "Day, Body", "heuristic, no source"),
        ("GMI", "3.31 + 0.02392 × mean glucose (mg/dL)", "glucose.py", "Body", "Bergenstal et al. 2018"),
    ]),
    ("Sleep", [
        ("Sleep score colour", "Garmin score 80+ green, under 60 red", "app.js", "Day readiness strip",
         "Garmin's own bands (inferred)"),
        ("Late session", "Gym or run starting at 19:00 or later followed by a sleep score under 70 = warning",
         "insights.py", "Day notes", "heuristic"),
        ("Short night", "Under 7 h counts as short", "advice.py", "Advice",
         "AASM/SRS adult minimum of 7 h (inferred)"),
        ("Irregular bedtime", "Sleep-onset standard deviation over 30 min = advice; over 60 min = alert",
         "advice.py, alerts.py", "Advice, Day notes, toasts", "heuristic"),
        ("Bedtime habit", "Asleep within 30 min of the median of the previous 14 nights", "habits.py", "Week",
         "heuristic"),
    ]),
    ("Recovery and readiness", [
        ("Readiness bands", "70+ green, 50–69 amber, under 50 red", "readiness.py BANDS", "Day, Recovery",
         "heuristic, checked by the built-in backtest against your logged off-episodes"),
        ("Signals", "Each costs points vs your own 28-day baseline: resting HR and HRV 9 per SD, sleep debt 9 per "
         "hour, training-load spike 35 per unit above 1.2, stress and body battery 4, feel 8 per point below 3",
         "readiness.py W", "Day, Recovery", "heuristic"),
        ("Noise band", "Within 0.5 SD of your baseline costs nothing", "readiness.py NOISE", "Day, Recovery",
         "heuristic"),
        ("Load spike", "7-day load ÷ 4-week load above 1.2", "readiness.py", "Day, Recovery",
         "acute:chronic workload ratio (Gabbett 2016, inferred)"),
        ("HRV dip", "HRV under 90% of your baseline (targets.yaml) = 'go easier'", "insights.py", "Day notes",
         "heuristic"),
        ("Resting HR rising", "7-day mean more than 2 SD above the 60-day baseline for 3+ days", "alerts.py",
         "Day notes, toasts", "heuristic"),
        ("vs normal", "Glance strip colours only gaps of 5 ms HRV or 3 bpm resting HR", "glance.py", "Day",
         "heuristic"),
    ]),
    ("Heart rate, runs and workouts", [
        ("HR zones", "Z1–Z5 at 50/60/70/80/90% of max HR", "workouts.py", "Training workout trace",
         "%HRmax five-zone model (Garmin default, inferred)"),
        ("Max HR", "The higher of 175 and your highest recorded session max", "workouts.py _max_hr",
         "Training", "heuristic floor"),
        ("Effort detection", "Heart-rate peak 8+ bpm above the low since the last peak, 45 s+ apart",
         "workouts.py _trace", "Training workout trace", "heuristic"),
        ("Recovery HR", "Drop in 2 min after stopping: 40+ excellent, 30+ good, 20+ fair, under 20 low",
         "app.js", "Training workout", "no source"),
        ("VO2 max drop", "Latest under 95% of the value about 3 months earlier", "alerts.py", "Day notes, toasts",
         "heuristic"),
    ]),
    ("Lifting and muscles", [
        ("Double progression", "All top sets at the top of the rep range: add the lift's smallest increment and "
         "drop to the bottom; any set below the range: hold; otherwise add a rep", "planner.py",
         "Training plan", "standard double progression"),
        ("Estimated 1RM", "kg × (1 + reps ÷ 30)", "data.py, workouts.py", "Training, personal-best stars",
         "Epley formula"),
        ("Personal best", "Estimated 1RM above every earlier session of that lift", "data.py", "Day, Training, Week",
         "design rule"),
        ("Warm-up sets", "Under 75% of the session's top weight are ignored for weekly sets", "planner.py",
         "Training volume", "heuristic"),
        ("Secondary muscles", "Count as half a set", "planner.py, muscles.py", "Training", "common convention"),
        ("Cardio on the muscle map", "10 minutes = 1 set for the main muscles", "muscles.py", "Training muscle map",
         "heuristic"),
    ]),
    ("Health score", [
        ("Scoring curve", "100 at the 'top' reference, 50 at 'average', 0 at 'poor', straight lines between",
         "healthscore.py", "Day, Longevity", "design; reference values in athlete.yaml (below)"),
        ("Unmeasured", "A marker never measured, or stale, counts as 50", "healthscore.py UNMEASURED",
         "Day, Longevity", "design rule: no credit for unknowns"),
        ("Stale after", "Labs, InBody and manual tests 400 days; watch, CGM and calculated 21 days",
         "healthscore.py STALE", "Day, Longevity", "heuristic"),
        ("Domain colours", "80+ green, 55+ amber, below red", "app.js", "Longevity", "heuristic"),
    ]),
    ("Advice and alerts", [
        ("Calories advice", "In range on under 60% of the last 7 closed days = act", "advice.py", "Advice",
         "heuristic"),
        ("Sodium", "14-day average over 2,300 mg = act", "advice.py", "Advice",
         "WHO 2,000 mg / US Dietary Guidelines 2,300 mg (inferred)"),
        ("Protein alert", "7-day protein under 1.4 g/kg", "alerts.py", "Day notes, toasts",
         "heuristic (below the 1.6 g/kg Morton 2018 plateau)"),
        ("Lifting frequency", "Under 2.5 gym sessions a week (30 days) = act", "advice.py", "Advice",
         "heuristic"),
        ("Cardio frequency", "Under 2 cardio sessions a week = act", "advice.py", "Advice", "heuristic"),
        ("Weigh-in", "No fasted weigh-in for more than 5 days = act", "advice.py", "Advice", "heuristic"),
        ("Weekly hit rate", "70%+ green, under 40% red", "app.js", "Week", "heuristic"),
    ]),
]

STATUS_RULES = ("Bands include the lower edge and exclude the upper. Green wins, then amber; anything outside both "
                "is red. 'contested' bands can make an in-range value amber, never red. 'lab' judges against the "
                "range printed on that lab report.")


def _band(b):
    if not b: return None
    lo, hi = b
    if lo is None: return f"under {hi}"
    if hi is None: return f"{lo} or more"
    return f"{lo} to under {hi}"


def build():
    tf = data._targets_file() or {}
    today = dt.date.today().isoformat()
    blocks = [b for b in (tf.get("intake") or []) if str(b.get("from")) <= today]
    cur = blocks[-1] if blocks else None
    targets = None
    if cur:
        k = cur.get("kcal") or {}
        rng = lambda v: f"{v[0]}–{v[1]}" if isinstance(v, (list, tuple)) else str(v)
        targets = {"label": cur.get("label"), "from": str(cur.get("from")),
                   "rows": [*([f"Calories, {t}", rng(v)] for t, v in k.items()),
                            *([["Protein", f"{cur['protein_g']['min']} g or more"]] if cur.get("protein_g") else []),
                            *([["Saturated fat", f"{cur['satfat_g']['max']} g or less"]] if cur.get("satfat_g") else []),
                            *([["Fibre", f"{cur['fibre_g']['min']} g or more"]] if cur.get("fibre_g") else []),
                            *([["Fat", f"{rng(cur['fat_g'])} g"]] if cur.get("fat_g") else []),
                            *([["Carbs", f"{rng(cur['carbs_g'])} g"]] if cur.get("carbs_g") else [])]}
    w = [x for x in (tf.get("weight") or []) if str(x.get("from")) <= today]
    pace = tf.get("pace") or {}
    ref = tf.get("reference") or {}
    REF_LABEL = {"easy_run_avg_hr_max": ("Easy runs average under", "bpm"), "hrv_baseline_ms": ("HRV baseline", "ms"),
                 "sleep_hours_min": ("Sleep target", "h"), "rhr_walk_only": ("Walk only when morning resting HR is at or above", "bpm"),
                 "steps_daily": ("Steps reference line", "a day")}
    personal = [[REF_LABEL.get(k, (k, ""))[0], f"{v} {REF_LABEL.get(k, ('', ''))[1]}".strip()] for k, v in ref.items()]
    tp = (data._load(data.ROOT / "exercises.yaml") or {}).get("training_plan") or {}
    if tp.get("rep_range"): personal.append(["Rep range", f"{tp['rep_range'][0]}–{tp['rep_range'][1]} reps"])
    if tp.get("working_sets"): personal.append(["Working sets", str(tp["working_sets"])])
    if tp.get("deload_every_weeks"): personal.append(["Deload", f"every {tp['deload_every_weeks']}th week"])
    if tp.get("weekly_sets_guide"): personal.append(["Weekly sets per muscle", f"{tp['weekly_sets_guide'][0]}–{tp['weekly_sets_guide'][1]} (over the top shows red)"])

    mk = data._load(data.ROOT / "markers.yaml") or {}
    cats = mk.get("categories") or {}
    markers = []
    for key, m in (mk.get("markers") or {}).items():
        bands = m.get("bands")
        markers.append({"key": key, "name": m.get("name", key), "cat": cats.get(m.get("cat"), m.get("cat") or ""),
                        "unit": m.get("unit", ""),
                        "green": "lab range" if bands == "lab" else None if bands == "none" else _band(m.get("green")),
                        "amber": None if bands in ("lab", "none") else _band(m.get("amber")),
                        "contested": _band(m.get("contested")), "verify": bool(m.get("verify")),
                        "every": "once" if m.get("once") else f"{m['interval_days']} days" if m.get("interval_days") else "continuous",
                        "note": m.get("note")})
    A = (data._load(data.ROOT / "athlete.yaml") or {}) if (data.ROOT / "athlete.yaml").exists() else {}
    am = A.get("markers") or {}
    domains = [{"label": lab, "weight": wt, "markers": [{"key": k, "weight": mw, **({kk: am.get(k, {}).get(kk) for kk in ("top", "avg", "poor", "unit", "verify")})}
                                                        for k, mw in ms.items()]} for _, lab, wt, ms in healthscore.DOMAINS]
    return data._jsonable({"rules": [{"section": s, "rows": [dict(zip(("threshold", "rule", "where", "shown", "basis"), r)) for r in rows]} for s, rows in RULES],
            "targets": targets, "weight": w[-1] if w else None,
            "pace": {"windows": pace.get("windows"), "share": pace.get("share"), "on_pace": pace.get("on_pace"), "behind": pace.get("behind")},
            "personal": personal, "markers": markers, "marker_rules": STATUS_RULES,
            "athlete": {"age": A.get("age"), "sex": A.get("sex"), "domains": domains}})
