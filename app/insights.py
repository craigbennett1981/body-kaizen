"""Rule-based daily insights for the Day view: wins (good), warnings (bad), observations (info).

Every rule reads only the repo data, so the notes are reproducible. Coach notes written in chat
live in the day file under `coach:` and are shown first.
"""
import datetime as dt
import data

def _f(v, d=0):
    return f"{v:,.{d}f}"

def _hrs(s):
    try:
        h, m = str(s).rstrip("m").split("h"); return int(h) + int(m) / 60
    except Exception:
        return None

def _hm(v):
    return f"{int(v)}h{round((v % 1) * 60):02d}"

def for_day(date):
    S = data.summary()
    idx = next((i for i, d in enumerate(S) if d["date"] == date), None)
    if idx is None:
        return []
    day = S[idx]
    detail = data.day_detail(date) or {}
    ref = data.reference()
    t, tg, ev = day.get("totals") or {}, day.get("targets") or {}, day.get("eval") or {}
    out = []
    add = lambda kind, text: out.append({"kind": kind, "text": text})
    complete = day.get("status") == "complete"

    # ---------- food ----------
    if day.get("status") == "unlogged":
        add("bad", "No food logged for this day.")
    if t and complete:
        # calories
        k, band = t["kcal"], tg.get("kcal")
        if band:
            lo, hi = band
            if k < lo: add("bad", f"Calories {_f(k)}, {_f(lo - k)} under the {day['day_type']}-day floor of {_f(lo)}. On a recomp that's a deficit; add roughly {_f(lo - k)} kcal, ideally as protein or carbs around training.")
            elif k > hi: add("bad", f"Calories {_f(k)}, {_f(k - hi)} over the {day['day_type']}-day ceiling of {_f(hi)}.")
            else: add("good", f"Calories {_f(k)}, inside the {_f(lo)}–{_f(hi)} {day['day_type']}-day target.")
        # protein
        pm = tg.get("protein_min")
        if pm:
            p = t["protein_g"]
            if p >= pm: add("good", f"Protein {_f(p)}g, target of {pm}g met.")
            else: add("bad", f"Protein {_f(p)}g, {_f(pm - p)}g short of {pm}g. That's about {'one scoop of whey' if pm - p <= 26 else f'{_f((pm - p) / 31 * 100)}g of chicken breast'}.")
        # saturated fat, with the biggest contributors
        sm = tg.get("satfat_max")
        if sm is not None:
            sf = t["satfat_g"]
            items = []
            for meal, its in (detail.get("meals") or {}).items():
                for it in its or []:
                    v = sum((c.get("macros") or {}).get("sf", 0) for c in it.get("parsed") or [])
                    if v >= 1: items.append((v, it["raw"]))
            items.sort(reverse=True)
            top = ", ".join(f"{r} ({v:.1f}g)" for v, r in items[:2])
            if sf <= sm: add("good", f"Saturated fat {sf:.1f}g, under the {sm}g limit.")
            else: add("bad", f"Saturated fat {sf:.1f}g, {sf - sm:.1f}g over the {sm}g limit. Biggest sources: {top}.")
        # fibre
        fm = tg.get("fibre_min")
        if fm:
            if t["fibre_g"] >= fm: add("good", f"Fibre {_f(t['fibre_g'])}g, target of {fm}g met.")
            else: add("bad", f"Fibre {_f(t['fibre_g'])}g, under {fm}g. Guava, chia, edamame or a bigger veg portion closes the gap.")
        # protein spread across feeds
        feeds = []
        for meal, its in (detail.get("meals") or {}).items():
            if meal == "snacks":
                continue
            feeds.append(sum((c.get("macros") or {}).get("p", 0) for it in its or [] for c in it.get("parsed") or []))
        snacks = [sum((c.get("macros") or {}).get("p", 0) for c in it.get("parsed") or []) for it in (detail.get("meals") or {}).get("snacks") or []]
        big = sum(1 for p in feeds + snacks if p >= 30)
        if pm and pm >= 150:
            add("info", f"Protein spread: {big} feed{'s' if big != 1 else ''} with 30g or more (aim for four of 35–40g).")
    if t and t.get("low_confidence_kcal_pct", 0) >= 15:
        add("info", f"{t['low_confidence_kcal_pct']}% of calories come from guessed portions, so treat the totals as rough.")

    # ---------- training ----------
    ex = (detail.get("exercise") or [])
    for e in ex:
        if e.get("type") == "run" and e.get("effort") == "easy" and (e.get("hr") or {}).get("avg"):
            hr = e["hr"]["avg"]; cap = ref.get("easy_run_avg_hr_max", 140)
            if hr <= cap: add("good", f"Easy run held at {hr} bpm average, under the {cap} cap.")
            else: add("bad", f"Easy run averaged {hr} bpm, over the {cap} cap. Slow down so easy stays easy.")
    # one summary line; the lifts themselves are starred in the Training panel
    try:
        prs = (data.day_detail(date) or {}).get("prs") or {}
        if prs:
            n = len(prs)
            add("good", f"{'New gym PB' if n == 1 else f'{n} new gym PBs'} today: " + ", ".join(l.replace("-", " ") for l in prs) + ". ★ in Training.")
    except Exception as e:
        print("pr note:", e, flush=True)
    if not ex and day["day_type"] == "rest":
        add("info", "Rest day: no sessions recorded.")

    # ---------- readiness ----------
    try:
        import readiness
        rd = next((x for x in readiness.series() if x["date"] == date), None)
    except Exception:
        rd = None
    if rd and rd["score"] is not None:
        names = {"rhr": "resting HR up", "hrv": "HRV down", "sleep_debt_h": "short sleep", "load": "training load spike",
                 "stress": "stress up", "bb": "low body battery", "feel": "feeling off"}
        why = ", ".join(names[k] for k in rd["drivers"])
        if rd["band"] == "green": add("good", f"Readiness {rd['score']}: normal for you.")
        elif rd["band"] == "amber": add("info", f"Readiness {rd['score']}: a bit below your normal" + (f" ({why})" if why else "") + ". Train, but don't chase bests.")
        else: add("bad", f"Readiness {rd['score']}: well below your normal" + (f" ({why})" if why else "") + ". Easy session or rest.")

    # ---------- recovery (this morning's readings) ----------
    r = day.get("recovery") or {}
    sl = _hrs(r.get("sleep"))
    if sl is not None:
        tgt = ref.get("sleep_hours_min", 7.5)
        if sl >= tgt: add("good", f"Slept {_hm(sl)}" + (f", score {r['sleep_score']}" if r.get("sleep_score") else "") + ".")
        else:
            week = [_hrs((d.get("recovery") or {}).get("sleep")) for d in S[max(0, idx - 6): idx + 1]]
            short = sum(1 for v in week if v is not None and v < tgt)
            add("bad", f"Slept {_hm(sl)}, under {_hm(tgt)}" + (f" — {short} short nights in the last 7" if short > 1 else "") + ".")
    if r.get("rhr") and r["rhr"] >= ref.get("rhr_walk_only", 52):
        add("bad", f"Resting HR {r['rhr']}, at or above {ref.get('rhr_walk_only', 52)}: walk only today.")
    base = ref.get("hrv_baseline_ms")
    if r.get("hrv_ms") and base and r["hrv_ms"] < base * 0.9:
        add("bad", f"HRV {r['hrv_ms']} ms, more than 10% under your {base} ms baseline. Go easier today.")
    # late session yesterday -> tonight's sleep
    if idx > 0:
        prev = S[idx - 1]
        late = [e for e in prev.get("exercise") or [] if e.get("start") and e["start"] >= "19:00" and e.get("type") in ("gym", "run")]
        if late and (r.get("sleep_score") or 100) < 70:
            n = 0   # how often has a late session been followed by a poor night, up to today?
            for i in range(1, idx + 1):
                pl = [e for e in S[i - 1].get("exercise") or [] if e.get("start") and e["start"] >= "19:00" and e.get("type") in ("gym", "run")]
                sc = (S[i].get("recovery") or {}).get("sleep_score")
                if pl and sc is not None and sc < 70: n += 1
            add("bad", f"Yesterday's {late[0]['type']} started at {late[0]['start']} and sleep scored {r['sleep_score']}."
                + (f" That's {n} times a late session has come before a poor night." if n > 1 else " Worth keeping sessions before 7pm."))

    # ---------- blood pressure ----------
    for b in ((detail.get("vitals") or {}).get("bp") or []):
        if not (b.get("sys") and b.get("dia")): continue
        cat = data.bp_category(b["sys"], b["dia"])
        txt = f"Blood pressure {b['sys']}/{b['dia']}" + (f", pulse {b['pulse']}" if b.get("pulse") else "")
        if cat == "normal": add("good", txt + ": normal.")
        elif cat == "elevated": add("info", txt + ": elevated systolic. One reading means little; watch the average.")
        elif cat == "crisis": add("bad", txt + ": crisis range. Re-measure after 5 minutes seated; if it's still this high, seek medical care now.")
        else: add("bad", txt + f": {cat} range. Re-measure seated after 5 quiet minutes; if the average stays here, raise it with your GP.")

    # ---------- steps ----------
    if day.get("steps") is not None:
        st, sref = day["steps"], ref.get("steps_daily", 10000)
        if st >= sref: add("good", f"{_f(st)} steps.")
        elif st < sref * 0.6: add("info", f"{_f(st)} steps, a quiet day on your feet.")

    # ---------- 7-day trends (complete days only) ----------
    win = [d for d in S[max(0, idx - 6): idx + 1] if d.get("status") == "complete" and d.get("totals")]
    if len(win) >= 4:
        under = sum(1 for d in win if (d["eval"].get("kcal") or {}).get("ok") is False and d["totals"]["kcal"] < (d["targets"].get("kcal") or [0])[0])
        if under >= len(win) * 0.6:
            add("bad", f"Under the calorie floor on {under} of the last {len(win)} logged days. The recomp needs maintenance calories.")
        ph = sum(1 for d in win if (d["eval"].get("protein_g") or {}).get("ok"))
        add("info" if ph < len(win) else "good", f"Protein target hit on {ph} of the last {len(win)} logged days.")
    streak = 0
    for d in reversed(S[: idx + 1]):
        e = (d.get("eval") or {}).get("satfat_g")
        if d.get("status") == "complete" and e and e.get("ok"): streak += 1
        else: break
    if streak >= 2:
        add("good", f"{streak} logged days running under the saturated fat limit.")
    wts = [(d["date"], d["weight"]["kg"]) for d in S[: idx + 1] if d.get("weight") and d["weight"].get("fasted") is not False]
    if wts:
        cur = dt.date.fromisoformat(date)
        this = [w for ds, w in wts if 0 <= (cur - dt.date.fromisoformat(ds)).days < 7]
        prev = [w for ds, w in wts if 7 <= (cur - dt.date.fromisoformat(ds)).days < 14]
        if this and prev:
            a, b = sum(this) / len(this), sum(prev) / len(prev)
            add("info", f"7-day weight average {a:.1f} kg ({a - b:+.1f} vs the week before; target {tg.get('weight_kg', '–')}).")

    # ---------- data ----------
    if not (detail.get("energy") or {}).get("source") and dt.date.fromisoformat(date) >= data.bkenv.start_date():
        add("info", "No watch data for this day yet.")

    # ---------- trend alerts (latest day only) ----------
    if idx == len(S) - 1 or date == data.bkenv.today().isoformat():
        try:
            import alerts
            for a in alerts.compute():
                if a["id"].startswith("lab-"): continue   # lab results live on the Longevity tab, not daily notes
                add("bad", f"{a['title']}. {a['text']} {a['todo']}")
        except Exception as e:
            print("alerts failed:", e, flush=True)

    order = {"bad": 0, "good": 1, "info": 2}
    out.sort(key=lambda x: order[x["kind"]])
    coach = [{**c, "coach": True} for c in (detail.get("coach") or [])]
    return coach + out

def last_watch_date():
    """Latest day the watch was clearly alive: a real step count, or (for days still in progress)
    a sync from the watch that day with a body-battery reading."""
    import json
    last = None
    for p in data.day_files():
        d = data._jsonable(data._load(p))
        if (d.get("energy") or {}).get("source") == "garmin" and (d.get("steps") or 0) > 500:
            last = d["date"]
    raw_dir = data.ROOT / "imports" / "garmin"
    for f in sorted(raw_dir.glob("*/*.json"))[-7:]:
        try:
            s = (json.load(open(f)).get("summary") or {})
        except Exception:
            continue
        sync = (s.get("lastSyncTimestampGMT") or "")[:10]
        if s.get("bodyBatteryMostRecentValue") is not None and sync >= f.stem[:10] and (last is None or f.stem > last):
            last = f.stem
    return last
