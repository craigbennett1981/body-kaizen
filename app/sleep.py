"""The Sleep tab: last night in detail, the trend against your target and Garmin's sleep need, how regular your
sleep is, what in your own days goes with better or worse nights, and advice built from all of that.

A night belongs to the day you wake up on (the 7 Nov file holds the night of 6-7 Nov). "The day before" a night is
the day you went to bed on: that's where its training, meals and caffeine are.

Comparisons are your own nights split by one thing at a time (late session or not, late meal or not), with how many
nights are on each side. They show what goes together in your data, not what causes what: a big day can mean both a
late session and a late night.
"""
import datetime as dt, statistics as st, json
import data

WINDOW = 90            # nights used for the comparisons
RECENT = 14            # nights used for "lately": regularity, debt, tonight's bedtime
LATE_SESSION = 19 * 60   # a session that ends after 19:00
LATE_MEAL = 20 * 60 + 30
CAFFEINE_FROM = 14 * 60
LATENCY_MIN = 15       # time to fall asleep assumed when working back from a wake time
MIN_NIGHTS = 5         # fewer than this on either side and a comparison is only a lead


def _mins(hhmm):
    try: h, m = map(int, str(hhmm)[:5].split(":")); return h * 60 + m
    except Exception: return None


def _hrs(s):
    """'7h18m' -> minutes."""
    try:
        s = str(s); h, m = s.split("h"); return int(h) * 60 + int((m or "0").rstrip("m") or 0)
    except Exception: return None


def _clock(m):
    """Minutes (may run past midnight or before it) -> 'HH:MM'."""
    if m is None: return None
    m = round(m) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _raw(day):
    try: return json.loads((data.ROOT / "imports" / "garmin" / day[:4] / f"{day}.json").read_text(encoding="utf-8"))
    except Exception: return {}


def _before_day(d):
    """What happened on the day before a night, from its day file and Garmin: session end, last meal, late caffeine."""
    n = data._nutrition()
    p = data.day_file(d)
    out = {"session_end": None, "last_meal": None, "caffeine_late_mg": 0.0, "caffeine": [], "steps": None, "stress": None,
           "satfat": None, "protein": None, "kcal": None}
    if p.exists():
        f = data._jsonable(data._load(p))
        tot = f.get("totals") or {}
        out["satfat"], out["protein"], out["kcal"] = tot.get("satfat_g"), tot.get("protein_g"), tot.get("kcal")
        for e in f.get("exercise") or []:
            s = _mins(e.get("start"))
            if s is not None and (e.get("kind") or e.get("type") or "") != "walk":
                out["session_end"] = max(out["session_end"] or 0, s + int(e.get("duration_min") or 45))
        for items in (f.get("meals") or {}).values():
            for it in items or []:
                t = _mins(it.get("time"))
                if t is None: continue
                out["last_meal"] = max(out["last_meal"] or 0, t)
                caf = sum((n.macros(c).get("caf", 0) or 0) for c in it.get("parsed") or [] if c.get("item") in n.FOODS)
                if caf: out["caffeine"].append((t, caf))
                if t >= CAFFEINE_FROM: out["caffeine_late_mg"] += caf
    sm = _raw(d).get("summary") or {}
    out["steps"] = sm.get("totalSteps"); out["stress"] = sm.get("averageStressLevel")
    return out


def nights(days=WINDOW, end=None):
    end = dt.date.fromisoformat(end) if end else data.bkenv.today()
    out = []
    for i in range(days - 1, -1, -1):
        d = (end - dt.timedelta(days=i)).isoformat()
        try: p = data.day_file(d)
        except ValueError: continue
        if not p.exists(): continue
        r = (data._jsonable(data._load(p)) or {}).get("recovery") or {}
        asleep = _hrs(r.get("sleep"))
        if not asleep or not r.get("sleep_start") or not r.get("sleep_end"): continue
        s, e = dt.datetime.fromisoformat(str(r["sleep_start"])[:16]), dt.datetime.fromisoformat(str(r["sleep_end"])[:16])
        mid = dt.datetime.combine(dt.date.fromisoformat(d), dt.time())
        st_ = r.get("sleep_stages_min") or {}
        dto = ((_raw(d).get("sleep") or {}).get("dailySleepDTO") or {})
        need = (dto.get("sleepNeed") or {}).get("actual") if isinstance(dto.get("sleepNeed"), dict) else None
        out.append({"date": d, "weekend_morning": dt.date.fromisoformat(d).weekday() >= 5,
                    "start": int((s - mid).total_seconds() // 60), "end": int((e - mid).total_seconds() // 60),   # minutes from the wake day's midnight
                    "asleep": asleep, "deep": st_.get("deep"), "light": st_.get("light"), "rem": st_.get("rem"), "awake": r.get("awake_min"),
                    "score": r.get("sleep_score"), "hrv": r.get("hrv_ms"), "rhr": r.get("rhr"), "spo2_low": r.get("spo2_low"),
                    "spo2_avg": r.get("spo2_avg"), "resp": r.get("respiration"), "stress": r.get("stress_avg"), "bb": r.get("body_battery"),
                    "need": need, "before": _before_day((dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat())})
    return out


def _avg(xs, nd=0):
    xs = [x for x in xs if x is not None]
    return (round(st.mean(xs), nd) if nd else round(st.mean(xs))) if xs else None


def _split(rows, name, test, yes, no):
    a = [r for r in rows if test(r) is True]; b = [r for r in rows if test(r) is False]
    if not a or not b: return None
    side = lambda g: {"n": len(g), "asleep": _avg([r["asleep"] for r in g]), "score": _avg([r["score"] for r in g]),
                      "hrv": _avg([r["hrv"] for r in g]), "bed": _avg([r["start"] for r in g])}
    A, B = side(a), side(b)
    return {"name": name, "yes": yes, "no": no, "a": A, "b": B, "enough": min(len(a), len(b)) >= MIN_NIGHTS,
            "d_asleep": (A["asleep"] - B["asleep"]) if A["asleep"] is not None and B["asleep"] is not None else None,
            "d_score": (A["score"] - B["score"]) if A["score"] is not None and B["score"] is not None else None,
            "d_hrv": (A["hrv"] - B["hrv"]) if A["hrv"] is not None and B["hrv"] is not None else None}


def factors(rows):
    med_steps = st.median([r["before"]["steps"] for r in rows if r["before"]["steps"]] or [0])
    med_stress = st.median([r["before"]["stress"] for r in rows if r["before"]["stress"] is not None] or [0])
    b = lambda r: r["before"]
    fs = [
        _split(rows, "Late session", lambda r: None if b(r)["session_end"] is None else b(r)["session_end"] >= LATE_SESSION,
               "session ended after 19:00", "session ended before 19:00"),
        _split(rows, "Trained that day", lambda r: b(r)["session_end"] is not None, "trained", "rest day"),
        _split(rows, "Late last meal", lambda r: None if b(r)["last_meal"] is None else b(r)["last_meal"] >= LATE_MEAL,
               "last food after 20:30", "last food before 20:30"),
        _split(rows, "Caffeine after 2 pm", lambda r: b(r)["caffeine_late_mg"] >= 40, "40 mg or more after 2 pm", "less"),
        _split(rows, "Busy day on your feet", lambda r: None if not b(r)["steps"] else b(r)["steps"] >= med_steps,
               f"{round(med_steps):,} steps or more", "fewer steps"),
        _split(rows, "Stressful day", lambda r: None if b(r)["stress"] is None else b(r)["stress"] > med_stress,
               "stress above your usual", "calmer day"),
        _split(rows, "Weekend", lambda r: r["weekend_morning"], "Saturday and Sunday mornings, when you can lie in", "weekday mornings"),
    ]
    return [f for f in fs if f]


def _sd(xs):
    xs = [x for x in xs if x is not None]
    return round(st.pstdev(xs)) if len(xs) >= 3 else None


def regularity(rows):
    wk = [r for r in rows if not r["weekend_morning"]]; we = [r for r in rows if r["weekend_morning"]]
    mid = lambda g: _avg([(r["start"] + r["end"]) / 2 for r in g])
    jet = (mid(we) - mid(wk)) if wk and we else None
    return {"bed_sd": _sd([r["start"] for r in rows]), "wake_sd": _sd([r["end"] for r in rows]),
            "bed_median": _clock(st.median([r["start"] for r in rows])) if rows else None,
            "wake_median": _clock(st.median([r["end"] for r in rows])) if rows else None,
            "wake_weekday": round(st.median([r["end"] for r in wk])) if wk else None,
            "wake_weekend": round(st.median([r["end"] for r in we])) if we else None,
            "social_jetlag_min": round(jet) if jet is not None else None,
            "late_nights": [r["date"] for r in rows if r["start"] >= 30]}   # asleep after 00:30


def tonight(rows, target_min, recent):
    """When to be in bed tonight: tomorrow's usual wake time, minus your target, your usual time awake in the night and
    time to fall asleep."""
    tomorrow = data.bkenv.today() + dt.timedelta(days=1)
    reg = regularity(recent)
    # always your weekday wake time: sleeping in at weekends is the habit to break, so it doesn't set tonight's bedtime
    wake = reg["wake_weekday"] if reg["wake_weekday"] is not None else reg["wake_weekend"]
    if wake is None: return None
    awake = round(st.median([r["awake"] for r in recent if r["awake"] is not None] or [0]))
    bed = wake - target_min - awake - LATENCY_MIN
    bed = 5 * round(bed / 5)
    return {"wake": _clock(wake), "in_bed": _clock(bed), "awake_min": awake, "latency_min": LATENCY_MIN, "target_min": target_min,
            "wind_down": _clock(bed - 45), "for": tomorrow.isoformat(), "weekend": tomorrow.weekday() >= 5}


def advice(rows, recent, target_min, F, reg, tn):
    """Rules on your own numbers first; each says what it saw. Ordered by how much they should move your sleep."""
    tips = []
    add = lambda pri, title, why, do: tips.append({"pri": pri, "title": title, "why": why, "do": do})
    avg = _avg([r["asleep"] for r in recent]); awake = _avg([r["awake"] for r in recent]); score = _avg([r["score"] for r in recent])
    if avg is not None and avg < target_min:
        short = target_min - avg
        broken = awake is not None and awake >= 40
        add(1, "You're short of sleep" + ("" if broken else ", not sleeping badly"),
            f"Last {len(recent)} nights you averaged {avg // 60}h {avg % 60:02d}m asleep, {short} min a night under your target"
            + (f", and you're only awake about {awake} min in the night." if not broken else f", with about {awake} min awake in the night."),
            (f"Your alarm sets the end of the night, so bedtime is the lever: in bed by {tn['in_bed']} for a {tn['wake']} wake-up." if tn else
             "Move your bedtime earlier; it's the only part of the night you control."))
    if reg["bed_sd"] and reg["bed_sd"] >= 45:
        add(2, "Your bedtime wanders",
            f"It varied by about {reg['bed_sd']} min (standard deviation) over the last {len(recent)} nights. Irregular sleep is linked to worse sleep and health even at the same total.",
            f"Set a wind-down alarm{(' for ' + tn['wind_down']) if tn else ''}: screens and work off, lights down. Same bedtime 7 nights a week, within 30 min.")
    if reg["late_nights"]:
        n = len(reg["late_nights"])
        add(2, f"{n} night{'s' if n != 1 else ''} asleep after 00:30",
            "In the last " + str(len(recent)) + " nights: " + ", ".join(dt.date.fromisoformat(d).strftime("%a %d %b").replace(" 0", " ") for d in reg["late_nights"]) + " (the morning you woke). With a fixed alarm, every late night is lost sleep.",
            "Find what those nights had in common (work, phone, a late session) and put a stop time on it.")
    if reg["social_jetlag_min"] is not None and reg["social_jetlag_min"] >= 45:
        add(3, "Weekend catch-up",
            f"The middle of your sleep moves {reg['social_jetlag_min']} min later at weekends. That's 'social jet lag': catching up on debt, then a harder Sunday night.",
            "Keep weekend wake-ups within an hour of weekdays; get the extra sleep by going to bed earlier instead.")
    for f in F:
        if f["name"] in ("Late session", "Late last meal", "Caffeine after 2 pm") and f["d_score"] is not None and (f["d_score"] <= -3 or (f["d_hrv"] or 0) <= -4):
            what = {"Late session": "finish training by 19:00", "Late last meal": "finish eating by 20:30",
                    "Caffeine after 2 pm": "make 2 pm your caffeine cut-off (decaf or rooibos after)"}[f["name"]]
            add(3 if f["enough"] else 4, f"{f['name']}: worse nights",
                f"Nights after a {f['yes']}: sleep score {f['a']['score']} vs {f['b']['score']}, HRV {f['a']['hrv']} vs {f['b']['hrv']} ms "
                f"({f['a']['n']} vs {f['b']['n']} nights{'' if f['enough'] else ', too few to be sure'}).",
                f"Try to {what}, and check this again in a month.")
    if awake is not None and awake >= 40:
        add(2, "Long spells awake",
            f"About {awake} min awake a night lately.",
            "If you're awake more than about 20 minutes, get up, keep the lights low, do something dull, and go back when sleepy. Bed is for sleep only. These habits come from CBT-I, a well-studied programme for poor sleep; if bad nights go on for weeks, ask a doctor about it.")
    lows = [r["spo2_low"] for r in recent if r["spo2_low"]]
    if len(lows) >= 5 and st.median(lows) < 88:
        add(4, "Low overnight oxygen readings",
            f"Your lowest SpO2 was a median {round(st.median(lows))}% over recent nights. Wrist readings are noisy, so this isn't a diagnosis.",
            "If you snore, wake with headaches or feel sleepy in the day, mention it to a doctor.")
    debt7 = sum(target_min - r["asleep"] for r in recent[-7:])   # net: a long night pays some back
    if debt7 >= 300:
        add(3, "Big sleep debt this week",
            f"{debt7 // 60}h {debt7 % 60:02d}m under target over the last 7 nights.",
            "Keep hard sessions honest but don't add volume this week; one or two early nights pay back more than a lie-in.")
    tips.sort(key=lambda t: t["pri"])
    return tips


GENERAL = [
    ("Fixed wake time, 7 days a week", "The strongest single habit. Your body clock sets itself from when you wake and see light, so a fixed wake time makes it easier to fall asleep at night."),
    ("Daylight in the first hour", "10–30 minutes outside after waking (shade counts; you're in Singapore). Morning light shifts your clock earlier, so sleepiness comes earlier."),
    ("Caffeine cut-off 8 hours before bed", "Caffeine has a half-life of about 5 hours. 400 mg even 6 hours before bed cut sleep by about an hour in a lab study (Drake 2013), and people didn't notice."),
    ("Wind down for 30–60 minutes", "Work, email and scrolling off; dim lights. Bright screens late delay sleep and make the next morning harder."),
    ("Cool, dark, quiet room", "Your core temperature has to drop to fall asleep. Aircon on, light covers, blackout blinds or an eye mask, earplugs if needed."),
    ("Hard training not too close to bed", "Evening exercise is fine for most people, but very hard sessions in the hour or two before bed can delay sleep. You've already seen late sessions wreck your nights."),
    ("Last big meal 2–3 hours before bed", "A big, late meal raises your heart rate and temperature overnight. A small protein snack (yogurt, milk) is fine."),
    ("Short, early naps only", "Under 30 minutes and before 3 pm, or not at all if you struggle to fall asleep at night."),
]


def build():
    tf = data.ROOT / "targets.yaml"
    target_h = _find(data._jsonable(data._load(tf)) if tf.exists() else {}, "sleep_hours_min") or 7.5
    target = round(target_h * 60)
    rows = nights()
    if not rows: return {"available": False, "target_min": target}
    recent = rows[-RECENT:]
    reg = regularity(recent)
    tn = tonight(rows, target, recent)
    F = factors(rows)
    last = rows[-1]
    stages = []
    for x in ((_raw(last["date"]).get("sleep") or {}).get("sleepLevels") or []):
        try:
            import daytimeline as T
            s, e = T._gmt_min(x["startGMT"], last["date"]), T._gmt_min(x["endGMT"], last["date"])
            stages.append({"start": s, "end": e, "stage": T.STAGE.get(int(x.get("activityLevel", 1)), "light")})
        except Exception: continue
    debt = 0; series = []
    for r in rows:
        debt += target - r["asleep"]; series.append({**{k: v for k, v in r.items() if k != "before"}, "debt": debt})
    return {"available": True, "target_min": target, "last": {**{k: v for k, v in last.items() if k != "before"}, "stages": stages,
            "before": last["before"]},
            "nights": series[-60:], "recent_n": len(recent),
            "recent": {"asleep": _avg([r["asleep"] for r in recent]), "score": _avg([r["score"] for r in recent]),
                       "awake": _avg([r["awake"] for r in recent]), "hrv": _avg([r["hrv"] for r in recent]),
                       "on_target": sum(r["asleep"] >= target for r in recent), "need": _avg([r["need"] for r in recent]),
                       "debt7": sum(target - r["asleep"] for r in recent[-7:])},
            "regularity": reg, "tonight": tn, "factors": F, "window_n": len(rows),
            "stages": stage_analysis(rows),
            "advice": advice(rows, recent, target, F, reg, tn), "general": [{"title": t, "text": x} for t, x in GENERAL]}


# ---------- stages: how much of each, where in the night, and what goes with more or less ----------

# Roughly what healthy adults get, as a share of time asleep. Watches estimate stages from movement and heart rate,
# so treat your numbers as a trend, not a lab measurement; deep sleep also falls with age.
TYPICAL = {"deep": (15, 25), "rem": (20, 25), "light": (50, 60)}


def _segments(day):
    """Last night's stages as (start, end, stage) in minutes from the wake day's midnight."""
    import daytimeline as T
    out = []
    for x in ((_raw(day).get("sleep") or {}).get("sleepLevels") or []):
        try: out.append((T._gmt_min(x["startGMT"], day), T._gmt_min(x["endGMT"], day), T.STAGE.get(int(x.get("activityLevel", 1)), "light")))
        except Exception: continue
    return out


def stage_analysis(rows):
    have = [r for r in rows if r["deep"] is not None and r["rem"] is not None and r["light"] is not None]
    if len(have) < 5: return {"available": False}
    A = lambda g, k: round(st.mean(r[k] for r in g if r[k] is not None)) if g else None
    pct = {k: round(100 * st.mean(r[k] / r["asleep"] for r in have), 1) for k in ("deep", "light", "rem")}
    groups = lambda spec: [{"label": lab, "n": len(g), **{k: A(g, k) for k in ("deep", "rem", "light", "awake", "score")}} for lab, g in spec if g]
    by_length = groups([("Under 6h 30m", [r for r in have if r["asleep"] < 390]), ("6h 30m to 7h 30m", [r for r in have if 390 <= r["asleep"] < 450]),
                        ("7h 30m or more", [r for r in have if r["asleep"] >= 450])])
    se = lambda r: r["before"]["session_end"]
    by_session = groups([("Session after 19:00", [r for r in have if se(r) and se(r) >= LATE_SESSION]),
                         ("Session before 19:00", [r for r in have if se(r) and se(r) < LATE_SESSION]), ("Rest day", [r for r in have if not se(r)])])
    by_bed = groups([("Asleep before midnight", [r for r in have if r["start"] < 0]), ("Midnight to 00:30", [r for r in have if 0 <= r["start"] < 30]),
                     ("After 00:30", [r for r in have if r["start"] >= 30])])
    # within the night: wake-ups, when they happen, and where deep and REM fall
    hours, after, counts, longest, d1, r2, first_deep, nseg = {}, {}, [], [], [], [], [], 0
    for r in have:
        sg = _segments(r["date"])
        if not sg: continue
        nseg += 1
        on, off = min(a for a, _, _ in sg), max(b for _, b, _ in sg); half = (on + off) / 2
        aw = [(a, b) for a, b, k in sg if k == "awake" and a > on]
        counts.append(len(aw)); longest.append(max([b - a for a, b in aw] or [0]))
        for a, _ in aw:
            h = (a // 60) % 24; hours[h] = hours.get(h, 0) + 1
            k = int((a - on) // 60); after[k] = after.get(k, 0) + 1
        D = sum(b - a for a, b, k in sg if k == "deep"); R = sum(b - a for a, b, k in sg if k == "rem")
        if D: d1.append(sum(max(0, min(b, half) - a) for a, b, k in sg if k == "deep") / D)
        if R: r2.append(sum(max(0, b - max(a, half)) for a, b, k in sg if k == "rem") / R)
        deep0 = [a for a, _, k in sg if k == "deep"]
        if deep0: first_deep.append(min(deep0) - on)
    order = sorted(hours, key=lambda h: (h + 12) % 24)
    wake = {"nights": nseg, "per_night": round(st.mean(counts), 1) if counts else None, "longest": round(st.mean(longest)) if longest else None,
            "long_nights": sum(x >= 20 for x in longest),
            "by_hour": [{"h": h, "count": hours[h], "per10": round(10 * hours[h] / nseg, 1)} for h in order] if nseg else [],
            "by_hours_in": [{"h": k, "count": after[k]} for k in sorted(after)]}
    arch = {"deep_first_half": round(100 * st.mean(d1)) if d1 else None, "rem_second_half": round(100 * st.mean(r2)) if r2 else None,
            "first_deep_min": round(st.median(first_deep)) if first_deep else None}
    out = {"available": True, "n": len(have), "avg": {k: A(have, k) for k in ("deep", "light", "rem", "awake", "asleep")}, "pct": pct,
           "typical": TYPICAL, "by_length": by_length, "by_session": by_session, "by_bedtime": by_bed, "wake": wake, "arch": arch}
    out["patterns"] = _stage_patterns(out)
    return out


def _stage_patterns(S):
    """Plain sentences for what stands out, biggest first. Each names the numbers it's built on."""
    P, pct, T = [], S["pct"], TYPICAL
    g = lambda lst, lab: next((x for x in lst if x["label"] == lab), None)
    if pct["rem"] < T["rem"][0]:
        short, long_ = g(S["by_length"], "Under 6h 30m"), g(S["by_length"], "7h 30m or more")
        tail = (f" Most of it comes late: {S['arch']['rem_second_half']}% of your REM is in the second half of the night, so the alarm cuts it."
                if S["arch"]["rem_second_half"] and S["arch"]["rem_second_half"] >= 65 else "")
        both = f" Short nights give you {short['rem']} min of REM; nights of 7h 30m or more give {long_['rem']} min." if short and long_ else ""
        P.append({"kind": "bad", "title": f"REM is low: {pct['rem']}% of your sleep", "text": f"Healthy adults get about {T['rem'][0]}–{T['rem'][1]}%." + tail + both
                  + " REM matters for memory, mood and learning skills, including new lifts. The surest way to get more is to sleep longer."})
    elif pct["rem"] >= T["rem"][0]:
        P.append({"kind": "good", "title": f"REM is in a healthy range: {pct['rem']}%", "text": f"Healthy adults get about {T['rem'][0]}–{T['rem'][1]}%."})
    late, early = g(S["by_session"], "Session after 19:00"), g(S["by_session"], "Session before 19:00")
    if late and early and late["n"] >= 3 and (early["rem"] - late["rem"] >= 10 or early["deep"] - late["deep"] >= 10):
        P.append({"kind": "bad", "title": "Late sessions cost you deep sleep and REM",
                  "text": f"After a session ending after 19:00: {late['deep']} min deep and {late['rem']} min REM, against {early['deep']} and {early['rem']} after an earlier one ({late['n']} vs {early['n']} nights)."})
    lb, eb = g(S["by_bedtime"], "After 00:30"), g(S["by_bedtime"], "Asleep before midnight")
    if lb and eb and lb["n"] >= 3 and eb["deep"] - lb["deep"] >= 10:
        P.append({"kind": "bad", "title": "Late nights cost deep sleep",
                  "text": f"Asleep after 00:30: {lb['deep']} min deep, against {eb['deep']} min when you're asleep before midnight ({lb['n']} vs {eb['n']} nights). Deep sleep comes early in the night and is strongest early in your body clock's night, so a late start loses some for good."})
    if pct["deep"] >= T["deep"][0]:
        P.append({"kind": "good", "title": f"Deep sleep is solid: {pct['deep']}%",
                  "text": f"Healthy adults get about {T['deep'][0]}–{T['deep'][1]}%, and it falls with age. {S['arch']['deep_first_half'] or '–'}% of yours comes in the first half of the night, as it should; your first deep sleep starts about {S['arch']['first_deep_min'] or '–'} min after you fall asleep."})
    W = S["wake"]
    if W["per_night"] is not None:
        peaks = sorted(W["by_hour"], key=lambda x: -x["count"])[:2]
        pk = " and ".join(f"{x['h']:02d}:00–{(x['h'] + 1) % 24:02d}:00" for x in sorted(peaks, key=lambda x: (x["h"] + 12) % 24))
        P.append({"kind": "bad" if W["long_nights"] >= W["nights"] * 0.25 else "info", "title": f"About {W['per_night']} wake-ups a night",
                  "text": f"Most often {pk}. Waking briefly a few times a night is normal and you usually won't remember it. Your longest spell awake averages {W['longest']} min, and {W['long_nights']} of {W['nights']} nights had one of 20 min or more."
                  + " If the same hour keeps showing up, look for a cause at that time: a toilet trip (fluids late), the aircon cycling, light, noise or a child."})
    return P


def _find(d, key):
    if isinstance(d, dict):
        if key in d: return d[key]
        for v in d.values():
            r = _find(v, key)
            if r is not None: return r
    return None
