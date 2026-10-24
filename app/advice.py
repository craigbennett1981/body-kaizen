"""Advice tab: practical advice per area, worked out from your own recent data.
Each item: level (act | keep | info), title, why (his numbers), do (concrete steps). Rule-based; no medical claims."""
import datetime as dt, statistics as st
from collections import defaultdict
import data, longevity

def _hrs(s):
    try: h, m = str(s).replace("m", "").split("h"); return int(h) + int(m) / 60
    except Exception: return None

def _mean(v, nd=0):
    v = [x for x in v if x is not None]
    return round(st.mean(v), nd) if v else None

def compute():
    S = data.summary()
    if not S: return {"sections": [], "top": []}
    today = dt.date.fromisoformat(S[-1]["date"])
    within = lambda d, n: (today - dt.date.fromisoformat(d["date"])).days < n
    comp14 = [d for d in S if within(d, 14) and d.get("status") == "complete" and d.get("totals")]
    last30 = [d for d in S if within(d, 30)]
    tg = data.targets_for(S[-1]["date"], "training")
    ref = data.reference()
    L = {m["id"]: m for m in longevity.compute()["markers"]}
    sec = defaultdict(list)
    def add(section, level, title, why, do, prio=5):
        sec[section].append({"level": level, "title": title, "why": why, "do": do, "prio": prio})

    # per-item totals over the last 14 complete days (for "where it comes from")
    src = defaultdict(lambda: defaultdict(float))
    for d in comp14:
        det = data.day_detail(d["date"]) or {}
        for meal in (det.get("meals") or {}).values():
            for e in meal or []:
                for it in e.get("parsed") or []:
                    m = it.get("macros") or {}
                    nm = it.get("name") or it.get("item")
                    for k, key in (("sf", "sf"), ("fib", "fib"), ("p", "p"), ("na", "na")):
                        src[key][nm] += m.get(k) or 0
    top = lambda key, n=3: [(k, round(v / max(len(comp14), 1), 1)) for k, v in sorted(src[key].items(), key=lambda x: -x[1])[:n]]
    nd = len(comp14)

    # ================= Diet =================
    if nd >= 3:
        T = lambda k: [d["totals"][k] for d in comp14]
        # calories: last 7 complete days, since targets changed recently
        c7 = comp14[-7:]; n7 = len(c7)
        dirs = [(d["eval"].get("kcal") or {}).get("dir") for d in c7]
        under, over, ok = dirs.count("under"), dirs.count("over"), sum(1 for d in c7 if (d["eval"].get("kcal") or {}).get("ok"))
        if ok < n7 * 0.6 and under >= over:
            gap = _mean([d["targets"]["kcal"][0] - d["totals"]["kcal"] for d in c7 if d["targets"].get("kcal") and d["totals"]["kcal"] < d["targets"]["kcal"][0]])
            add("Diet", "act", "Eat enough for the recomp",
                f"Under your calorie floor on {under} of the last {n7} logged days, by about {gap:.0f} kcal. At maintenance you can build muscle while losing fat; in a deficit the muscle side stalls.",
                [f"Add roughly {gap:.0f} kcal on training days: an extra bowl of rice (~200 kcal), a banana with Greek yogurt (~250), or a second shake made with milk (~280).",
                 "Put most of it around training: a carb + protein meal within 2 hours after the gym."], 1)
        elif ok < n7 * 0.6:
            add("Diet", "act", "Calories are running over", f"Over the ceiling on {over} of the last {n7} logged days.", ["Trim the biggest snack or dinner portion first, not protein."], 2)
        else:
            add("Diet", "keep", "Calories are about right", f"In range on {ok} of the last {n7} logged days.", ["Keep doing what you're doing."], 8)
        # protein
        pmin = tg.get("protein_min") or 150
        p = _mean(T("protein_g")); hit = sum(1 for d in comp14 if (d["eval"].get("protein_g") or {}).get("ok"))
        if p is not None and p < pmin:
            add("Diet", "act", "Get protein up to 150 g", f"Average {p:.0f} g/day; hit {pmin} g on {hit} of {nd} days.",
                ["Four feeds of 35–40 g: breakfast, lunch, post-training shake, dinner.",
                 "Easy adds: Greek yogurt (≈20 g a tub), 2 extra eggs (12 g), a tin of tuna (25 g), chicken breast (30 g per 100 g)."], 2)
        elif p is not None:
            add("Diet", "keep", "Protein is on target", f"Average {p:.0f} g/day (target {pmin}).", ["Keep spreading it across 4 meals."], 8)
        # sat fat
        smax = tg.get("satfat_max") or 20
        sf = _mean(T("satfat_g"), 1); sfo = sum(1 for v in T("satfat_g") if v > smax)
        tops = ", ".join(f"{k} ({v} g/day)" for k, v in top("sf"))
        if sf is not None and (sf > smax or sfo):
            add("Diet", "act", "Cut saturated fat", f"Average {sf} g/day against a limit of {smax}; over on {sfo} of {nd} days. Biggest sources: {tops}.",
                [f"Start with the biggest source ({top('sf', 1)[0][0] if src['sf'] else 'fatty meat'}): eat less of it or swap it for a leaner option.",
                 "Lean cuts, chicken or fish instead of fatty pork and beef mince; low-fat dairy; skip butter and ghee.",
                 "Cook with olive or canola oil instead of butter, lard or coconut oil.",
                 "Watch coconut milk (curries, laksa), pastries, cheese and fried hawker food."], 1)
        elif sf is not None:
            add("Diet", "keep", "Saturated fat is under control", f"Average {sf} g/day (limit {smax}). Biggest sources: {tops}.", ["Hold the line: ApoB is the reason this matters."], 6)
        # fibre
        fmin = tg.get("fibre_min") or 30
        fb = _mean(T("fibre_g"))
        if fb is not None and fb < fmin:
            add("Diet", "act", "Eat more fibre", f"Average {fb:.0f} g/day against {fmin} g. Best sources now: " + ", ".join(f"{k} ({v} g)" for k, v in top("fib")) + ".",
                ["Oats or chia at breakfast (+5–8 g); oats also carry beta-glucan, which lowers LDL.",
                 "A cup of beans, lentils or chickpeas a day (+10–15 g).",
                 "Two fist-sized portions of veg at lunch and dinner, and fruit as the snack (berries, guava, pear).",
                 "Switch white rice/bread to brown rice, wholemeal or multigrain where you can."], 2)
        elif fb is not None:
            add("Diet", "keep", "Fibre is on target", f"Average {fb:.0f} g/day.", ["Keep the oats and veg going."], 8)
        # sodium
        na = _mean(T("sodium_mg"))
        if na and na > 2300:
            add("Diet", "act", "Ease off salt", f"Average {na:.0f} mg sodium/day; the usual ceiling is 2,000–2,300 mg. Top sources: " + ", ".join(k for k, _ in top("na")) + ".",
                ["Go easy on soy sauce, stock cubes, processed meat and soup broths (leave the soup).", "Check labels: under 120 mg per 100 g is low-salt."], 4)
    else:
        add("Diet", "info", "Not enough logged days", f"Only {nd} complete days in the last two weeks.", ["Log every meal for a week so the advice here is based on real numbers."], 1)

    # ================= Heart & blood =================
    ab, ldl = L.get("apob", {}), L.get("ldl", {})
    h_ab = ab.get("history") or []
    if ldl.get("status") in ("red", "amber"):
        add("Heart & blood", "act", "Bring LDL under 3.4", f"LDL {ldl.get('value')} mmol/L against a target of under 3.4 for low cardiovascular risk (ApoB {ab.get('value')} g/L, tracked)." + (lambda h: f" LDL is down from {max(v for _, v in h)} at its peak, so the diet changes are working; another 0.3 gets you there. ApoB has barely moved ({h_ab[0][1]} → {ab['value']})." if h and h_ab else "")(ldl.get("history") or []),
            ["Keep saturated fat under 20 g/day (see Diet).", "Add 5–10 g soluble fibre: a bowl of oats plus 1–2 tsp psyllium husk daily.",
             "Plant sterols (fortified milk or yogurt drink, 2 g/day) lower LDL by roughly 8–10%.",
             "Ask your doctor for your 10-year cardiovascular risk score: at higher risk the LDL target is usually lower (often 2.6 or 1.8)."], 1)
    crp = L.get("hscrp", {})
    if crp.get("status") in ("amber", "red"):
        add("Heart & blood", "info", "Recheck hs-CRP", f"hs-CRP {crp['value']} mg/L. A cold or a hard session can push it up temporarily.",
            ["Retest after 2–4 weeks of feeling well and an easy 48 hours before the draw."], 5)
    b12 = L.get("b12", {})
    if b12.get("status") in ("amber", "red") and (b12.get("value") or 0) > 569:
        add("Heart & blood", "info", "B12 is above range", f"B12 {b12['value']} pmol/L. You take methyl-B12 on some days, which explains it; a high reading from supplements is generally harmless.", ["Mention the supplement to your doctor so the result isn't chased.", "If you want it back in range, take it less often rather than more."], 6)
    bp = [b for b in data.bp_readings() if (today - dt.date.fromisoformat(b["date"])).days < 60]
    if bp:
        s_, d_ = round(st.mean(b["sys"] for b in bp)), round(st.mean(b["dia"] for b in bp))
        add("Heart & blood", "keep" if s_ < 120 and d_ < 80 else "act", "Blood pressure", f"Average {s_}/{d_} over {len(bp)} readings in the last 60 days.",
            ["Keep checking once a week, same time of day, seated and rested for 5 minutes."], 7)

    # ================= Training =================
    gym = [e for d in last30 for e in d["exercise"] if e.get("type") == "gym"]
    cardio = [e for d in last30 for e in d["exercise"] if e.get("type") in ("run", "swim", "ruck")]
    wk = max(len({d["date"] for d in last30}) / 7, 1)
    gpw, cpw = len(gym) / wk, len(cardio) / wk
    if gpw < 2.5:
        add("Training", "act", "Lift at least 3 times a week", f"{gpw:.1f} gym sessions/week over the last 30 days.", ["Three full-body sessions; each lift 3 sets in the 8–12 range, adding weight when you hit 12."], 3)
    else:
        add("Training", "keep", "Strength training is consistent", f"{gpw:.1f} gym sessions/week.", ["Keep adding weight or reps; the Training tab shows next targets."], 7)
    if cpw < 2:
        add("Training", "act", "More easy cardio", f"{cpw:.1f} cardio sessions/week.", ["Two or three 40-minute zone 2 sessions (you can talk in full sentences).", f"Keep easy runs under {ref.get('easy_run_avg_hr_max', 140)} bpm average."], 4)
    else:
        add("Training", "keep", "Cardio volume is good", f"{cpw:.1f} cardio sessions/week (runs, swims, rucks).",
            [f"Keep most of it easy (average HR under {ref.get('easy_run_avg_hr_max', 140)}); one harder interval session a week builds VO2max."], 7)
    if L.get("grip", {}).get("value") is None:
        add("Training", "act", "Do the baseline fitness tests", "Grip strength, sit-to-stand and one-leg stand are three of the strongest predictors of healthy ageing, and they've never been measured.",
            ["10 minutes: grip both hands (best of 3), 30-second sit-to-stand, one-leg stand eyes open, waist at the navel. Send me the numbers."], 3)

    # ================= Sleep & recovery =================
    rec = [d["recovery"] for d in last30 if d.get("recovery")]
    sl = _mean([_hrs(r.get("sleep")) for r in rec], 2)
    short = sum(1 for r in rec if (_hrs(r.get("sleep")) or 9) < 7)
    if sl is not None and sl < ref.get("sleep_hours_min", 7.5):
        add("Sleep & recovery", "act", "Get more sleep", f"Average {int(sl)}h{round(sl % 1 * 60):02d} a night; under 7 hours on {short} of {len(rec)} nights. Your target is 7h30.",
            ["Move lights-out 30 minutes earlier: wake time is fixed, so bedtime is the lever.", "Screens away and room cool (24–26 °C) 30 minutes before bed.",
             "No caffeine after 2 pm."], 2)
    elif sl is not None:
        add("Sleep & recovery", "keep", "Sleep length is good", f"Average {sl:.1f} h a night.", ["Keep it."], 8)
    osd = L.get("sleep_onset_sd", {}).get("value")
    if osd and osd > 30:
        add("Sleep & recovery", "act", "Make bedtime regular", f"Your bedtime varies by about {osd:.0f} min night to night. Regular timing predicts health independently of sleep length.",
            ["Pick a lights-out time and keep it within 30 minutes, weekends included."], 4)
    if not any((d.get("recovery") or {}).get("source") == "garmin" for d in S[-3:]):
        add("Sleep & recovery", "act", "Wear and charge the watch", "No watch data for the last few days, so sleep, HRV and readiness can't be tracked.",
            ["Fix the charger and wear it overnight."], 3)

    # ================= Body =================
    wt = [(d["date"], d["weight"]["kg"]) for d in S if d.get("weight") and d["weight"].get("fasted") is not False]
    wtar = data.weight_target_for(S[-1]["date"])
    if wt:
        last = wt[-1]
        add("Body", "info", "Weight and recomp", f"Last fasted weight {last[1]} kg ({dt.date.fromisoformat(last[0]).strftime('%-d %b')}); target {wtar} kg. On a recomp the scale moves slowly: judge it on the InBody rescan in early December.",
            ["Weigh 3+ mornings a week, fasted, after the toilet.", "Expect weight to hold roughly steady while fat drops and muscle rises."], 6)
        if (today - dt.date.fromisoformat(last[0])).days > 5:
            add("Body", "act", "Weigh in again", f"No fasted weigh-in since {dt.date.fromisoformat(last[0]).strftime('%-d %b')}.", ["Step on the scale tomorrow morning."], 4)

    # ================= Lifestyle =================
    feel = sum(1 for d in last30 if d.get("feel"))
    if feel < 5:
        add("Lifestyle", "act", "Log how you feel", "Your off days so far came without warning from the watch. A daily score is the cheapest early warning.",
            ["Add one line when you log: 'feel 4 gut 3 energy 4' (1–5)."], 5)
    st_ = _mean([d.get("steps") for d in last30 if d.get("steps") and d["steps"] > 500])
    if st_:
        add("Lifestyle", "keep" if st_ >= ref.get("steps_daily", 10000) else "act", "Daily steps",
            f"Average {st_:,.0f} steps/day.", ["Keep it above 10,000: walk calls, take stairs, a 15-minute walk after dinner also helps blood sugar."], 7)

    order = ["Diet", "Heart & blood", "Training", "Sleep & recovery", "Body", "Lifestyle"]
    sections = [{"name": n, "items": sorted(sec[n], key=lambda x: (x["level"] != "act", x["prio"]))} for n in order if sec.get(n)]
    allact = sorted([dict(i, section=s["name"]) for s in sections for i in s["items"] if i["level"] == "act"], key=lambda x: x["prio"])
    return {"as_of": S[-1]["date"], "days_logged": nd, "top": allact[:3], "sections": sections}
