"""Lift planner: next-session targets by double progression, weekly sets per muscle, deload weeks."""
import datetime as dt, re
import data

SET = re.compile(r"^([\d.]+)x(\d+)$"); CARRY = re.compile(r"^([\d.]+)kg@(\d+)m$"); HOLD = re.compile(r"^(\d+)s$")

def _cat():
    return data._load(data.ROOT / "exercises.yaml")

def plan_info(today=None):
    tp = _cat().get("training_plan") or {}
    start = dt.date.fromisoformat(str(tp.get("block_start") or data.bkenv.start_date()))
    today = today or data.bkenv.today()
    week_no = (today - start).days // 7 + 1
    every = tp.get("deload_every_weeks", 4)
    deload_now = week_no >= 1 and week_no % every == 0
    next_deload = start + dt.timedelta(weeks=(week_no // every + (0 if deload_now else 1)) * every - 1)
    return {"block_start": start.isoformat(), "week": week_no, "deload_now": deload_now,
            "next_deload_week_of": next_deload.isoformat(), "every": every, "rep_range": tp.get("rep_range", [8, 12]),
            "working_sets": tp.get("working_sets", 3), "weekly_sets_guide": tp.get("weekly_sets_guide", [10, 20])}

def history():
    """{lift: [(date, [parsed sets])]} oldest first."""
    out = {}
    for p in data.day_files():
        d = data._jsonable(data._load(p))
        for e in d.get("exercise") or []:
            for l in e.get("lifts") or []:
                sets = []
                for s in l.get("sets") or []:
                    s = str(s)
                    if m := SET.match(s): sets.append({"kg": float(m[1]), "reps": int(m[2])})
                    elif m := CARRY.match(s): sets.append({"kg": float(m[1]), "m": int(m[2])})
                    elif m := HOLD.match(s): sets.append({"s": int(m[1])})
                if sets: out.setdefault(l["ex"], []).append((d["date"], sets))
    return out

def _r(x):
    return round(x, 1)   # machine stacks step in odd amounts (31.8 -> 36.3), so keep 0.1 kg

def next_target(lift, sessions, cat, info):
    spec = cat["lifts"].get(lift, {})
    date, sets = sessions[-1]
    lo, hi = spec.get("rep_range", info["rep_range"])
    n = info["working_sets"]
    partial = len(sets) < n
    if "m" in sets[0]:   # farmers walk: distance first, then load
        kg = max(s["kg"] for s in sets); top = [s for s in sets if s["kg"] == kg]
        dlo, dhi = spec.get("distance_range_m", [60, 80])
        if len(top) >= n and min(s["m"] for s in top) >= dhi:
            return {"target": f"{n} × {_r(kg + spec.get('increment_kg', 5))} kg for {dlo} m", "rule": f"all sets reached {dhi} m: add weight, back to {dlo} m"}
        m = min(dhi, max(s["m"] for s in top) + spec.get("distance_step_m", 20))
        return {"target": f"{n} × {kg} kg for {m} m", "rule": f"build distance to {dhi} m before adding weight"}
    if "s" in sets[0]:
        t = max(s["s"] for s in sets); tlo, thi = spec.get("time_range_s", [45, 90])
        return {"target": f"{n} × {min(thi, t + spec.get('increment_s', 15))}s", "rule": "add time to the top of the range"}
    rs = spec.get("reset")   # temporary back-off: hold a lighter weight until it's done cleanly
    if rs:
        done = any(d >= str(rs["from"]) and sum(1 for x in ss if x.get("kg", 0) >= rs["kg"] and x.get("reps", 0) >= rs["reps"]) >= n
                   for d, ss in sessions)
        if not done:
            return {"target": f"{n} × {rs['reps']} at {rs['kg']} kg, strict", "rule": rs.get("why", "back-off to rebuild form")}
    base = ""
    if len(sessions) > 1 and not (rs and date >= str(rs["from"])):   # a one-off lighter session (tired, other machine) shouldn't drag the plan down
        pdate, psets = sessions[-2]
        pkg = max((x.get("kg", 0) for x in psets), default=0)
        if pkg > max(x.get("kg", 0) for x in sets) and (dt.date.fromisoformat(date) - dt.date.fromisoformat(pdate)).days <= 10:
            date, sets = pdate, psets; partial = len(sets) < n
            base = f"; last session was lighter, so working from {pdate}"
    kg = max(s["kg"] for s in sets); top = [s for s in sets if s["kg"] == kg]
    reps = [s["reps"] for s in top]
    inc = spec.get("increment_kg", 2.5)
    at = lambda w: "bodyweight" if not w else f"{w} kg"
    if len(top) >= n and min(reps) >= hi:
        return {"target": f"{n} × {lo} at {at(_r(kg + inc))}{' + belt' if not kg else ''}", "rule": f"hit {hi} reps on every set: add {inc} kg, back to {lo}{base}"}
    if min(reps) < lo:
        return {"target": f"{n} × {lo} at {at(kg)}", "rule": f"below {lo} reps last time: hold the weight until {lo} is solid{base}"}
    goal = min(hi, max(reps) + 1)
    note = " (last log had fewer than 3 sets at this weight)" if partial or len(top) < n else ""
    if not kg:   # bodyweight: build total reps
        return {"target": f"{n} sets, beat {sum(reps)} total reps ({'/'.join(str(r) for r in reps)} last time)", "rule": f"add reps until {n} × {hi}, then add {inc} kg with a belt{base}"}
    return {"target": f"{n} × {goal} at {at(kg)}", "rule": f"add a rep per set until {hi}, then add {inc} kg{note}{base}"}

def weekly_sets(weeks=4, today=None):
    cat = _cat()["lifts"]; today = today or data.bkenv.today()
    monday = today - dt.timedelta(days=today.weekday())
    out = []
    for w in range(weeks - 1, -1, -1):
        start = monday - dt.timedelta(weeks=w); end = start + dt.timedelta(days=6)
        counts = {}
        for lift, sess in history().items():
            spec = cat.get(lift, {})
            for date, sets in sess:
                if start.isoformat() <= date <= end.isoformat():
                    top = max((s.get("kg", 0) for s in sets), default=0)
                    work = [s for s in sets if "kg" not in s or s["kg"] >= 0.75 * top]   # ramp-up sets are warm-ups
                    for m in spec.get("muscles", []): counts[m] = counts.get(m, 0) + len(work)
                    for m in spec.get("secondary", []): counts[m] = counts.get(m, 0) + 0.5 * len(work)
        out.append({"week_of": start.isoformat(), "sets": {k: round(v, 1) for k, v in sorted(counts.items())}})
    return out

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

def week_plan(today=None):
    """The next 7 days from training_plan.week in exercises.yaml: what each day is for, run details with this week's
    interval step, the extras for every gym session, and when the next run test is due. None if there's no week set."""
    tp = _cat().get("training_plan") or {}
    wk = tp.get("week")
    if not wk: return None
    today = today or data.bkenv.today()
    start = tp.get("week_from") or tp.get("block_start")
    start = dt.date.fromisoformat(str(start)) if start else today
    runs = tp.get("runs") or {}
    days = []
    for k in range(7):
        d = today + dt.timedelta(days=k)
        spec = dict(wk.get(DAYS[d.weekday()]) or {})
        wn = max(0, (d - start).days // 7)
        if spec.get("kind") == "run":
            ses = spec.get("session")
            if isinstance(ses, list): ses = ses[wn % len(ses)]
            r = runs.get(ses) or {}
            spec = {**spec, "session": ses, "name": r.get("name", str(ses)), "detail": r.get("detail")}
            prog = r.get("progression")
            if prog: spec["step"] = prog[min(wn, len(prog) - 1)] if d >= start else prog[0]
        days.append({"date": d.isoformat(), "dow": DAYS[d.weekday()], **spec})
    test = tp.get("run_test") or {}
    nxt = None
    if test.get("baseline", {}).get("date") and test.get("every_weeks"):
        b = dt.date.fromisoformat(str(test["baseline"]["date"]))
        nxt = b + dt.timedelta(weeks=int(test["every_weeks"]))
        while nxt < today: nxt += dt.timedelta(weeks=int(test["every_weeks"]))
    return data._jsonable({"days": days, "every_gym": tp.get("every_gym") or [], "tendon_rule": tp.get("tendon_rule"),
            "run_test": {**test, "next": nxt.isoformat() if nxt else None} if test else None})

def plan(today=None):
    info = plan_info(today); cat = _cat(); H = history()
    rows = []
    for lift, sess in sorted(H.items(), key=lambda kv: kv[1][-1][0], reverse=True):
        t = next_target(lift, sess, cat, info)
        last_date, last = sess[-1]
        last_txt = ", ".join(f"{s['kg']}×{s['reps']}" if "reps" in s else f"{s['kg']}kg@{s['m']}m" if "m" in s else f"{s['s']}s" for s in last)
        if info["deload_now"]:
            t = {"target": f"2 sets, same weight as last time, stop 2–3 reps short", "rule": "deload week"}
        rows.append({"lift": lift, "last_date": last_date, "last": last_txt, "sessions": len(sess), **t})
    return {"info": info, "lifts": rows, "volume": weekly_sets(4, today), "week": week_plan(today)}
