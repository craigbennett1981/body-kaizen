"""Trend alerts from the longevity brief. Each comes with what to do about it.
Shown as notes on the latest day and as dashboard toasts."""
import datetime as dt, statistics as st
import data, longevity

FRESH_DAYS = 10   # ignore a signal whose newest data point is older than this

def _d(s): return dt.date.fromisoformat(str(s)[:10])

def compute(today=None):
    today = today or data.bkenv.today()
    L = longevity.compute(); M = {m["id"]: m for m in L["markers"]}
    for m in M.values():   # never look past `today` (lets the rules be replayed over history)
        m["history"] = [h for h in m["history"] if _d(h[0]) <= today]
    C = longevity.cfg()["markers"]
    out = []
    add = lambda id_, since, title, text, todo: out.append({"id": id_, "since": str(since), "kind": "bad", "title": title, "text": text, "todo": todo})
    fresh = lambda d: d and (today - _d(d)).days <= FRESH_DAYS

    # 1. Resting HR: 7-day mean above 60-day baseline + 2 SD for 3+ days running
    S = data.summary()
    rhr = [(_d(d["date"]), (d.get("recovery") or {}).get("rhr")) for d in S]
    rhr = [(d, v) for d, v in rhr if v and d <= today]
    run, first = 0, None
    for i, (d, _) in enumerate(rhr):
        w7 = [v for dd, v in rhr if 0 <= (d - dd).days < 7]
        base = [v for dd, v in rhr if 7 <= (d - dd).days < 67]
        if len(w7) >= 4 and len(base) >= 20 and st.mean(w7) > st.mean(base) + 2 * st.pstdev(base):
            run += 1; first = first or d
        else:
            run, first = 0, None
    if run >= 3 and fresh(rhr[-1][0]):
        add("rhr", first, "Resting heart rate is up",
            f"Your 7-day resting HR has been more than 2 SD above your 60-day baseline for {run} days.",
            "Often an early sign of illness, poor sleep or overreaching. Take easy days, prioritise sleep, and hold off on hard sessions until it settles.")

    # 2. VO2max down more than 5% over 90 days
    v = [(_d(d), x) for d, x in M["vo2max"]["history"]]
    if v and fresh(v[-1][0]):
        d1, x1 = v[-1]
        old = [x for d, x in v if 76 <= (d1 - d).days <= 104]
        if old and x1 < old[0] * 0.95:
            add("vo2", d1, "VO2max has dropped",
                f"VO2max {x1:g}, down {100 * (1 - x1 / old[0]):.0f}% from {old[0]:g} about 90 days ago.",
                "Check for a training gap or illness. Keep 2–3 zone 2 sessions and one interval session a week.")

    # 3. A lab marker moved into amber or red at the latest draw
    labs = [l for l in longevity._yaml("labs.yaml") if _d(l["date"]) <= today]
    if labs:
        latest = max(labs, key=lambda x: str(x["date"]))
        if (today - _d(latest["date"])).days <= 120:
            rank = {"green": 0, "grey": 0, "amber": 1, "red": 2}
            for r in latest.get("results") or []:
                k = r["marker"]; m = C.get(k)
                if not m: continue
                ref = (r.get("ref_low"), r.get("ref_high"))
                now = longevity.status(m, r["value"], ref)
                prev = [x for x in M[k]["history"] if _d(x[0]) < _d(latest["date"])] if k in M else []
                was = longevity.status(m, prev[-1][1], ref) if prev else None
                if rank[now] > 0 and (was is None or rank[now] > rank[was]):
                    add(f"lab-{k}", latest["date"], f"{m['name']} is {'off target' if now == 'red' else 'in the amber zone'}",
                        f"{m['name']} {r['value']:g} {r.get('unit','')} on {_d(latest['date']).strftime('%-d %b')}" + (f", was {prev[-1][1]:g}" if prev else ", first result") + ".",
                        (longevity.WHY.get(k) or "") + " Discuss it with your doctor; the Longevity tab shows the target range.")

    # 4. Protein under 1.4 g/kg (7-day average of complete days)
    p = M["protein_gkg"]["history"]
    if p and fresh(p[-1][0]) and p[-1][1] < 1.4:
        add("protein", p[-1][0], "Protein is low",
            f"7-day average protein is {p[-1][1]:.2f} g/kg, under the 1.4 g/kg floor.",
            "Add a protein serve at the lightest meal, e.g. a shake, Greek yogurt or eggs.")

    # 5. Sleep timing irregular: onset SD over 60 min across 14 days
    s = M["sleep_onset_sd"]["history"]
    if s and fresh(s[-1][0]) and s[-1][1] > 60:
        add("onset", s[-1][0], "Bedtime is irregular",
            f"Your sleep onset has varied by {s[-1][1]:.0f} min (SD) over the last 14 nights.",
            "Pick a fixed lights-out time and keep it within 30 minutes, weekends included.")
    return out
