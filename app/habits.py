"""Habits: daily pass/fail for longevity habits, weekly values against targets, and a 12-week grid."""
import datetime as dt, statistics as st
import data, longevity

HABITS = [  # id, label, daily test description
    ("steps", "Steps ≥ 7,000"), ("aerobic", "Moved ≥ 21 aerobic min"), ("strength", "Strength session"),
    ("protein", "Protein ≥ 1.6 g/kg"), ("fibre", "Fibre ≥ 30 g"), ("satfat", "Sat fat < 10% energy"),
    ("sleep", "Slept 7–9 h"), ("bedtime", "Bedtime within 30 min of usual"),
]

def daily(weeks=12):
    S = data.summary(); files = data.day_files()
    det = {d["date"]: data._jsonable(data._load(p)) for d, p in zip(S, files)}
    days = [d["date"] for d in S][-weeks * 7:]
    idx = {d["date"]: i for i, d in enumerate(S)}
    out = []
    for ds in days:
        d = S[idx[ds]]; x = det[ds]; r = x.get("recovery") or {}; t = d.get("totals") if d.get("status") == "complete" else None
        # 7-day weight for g/kg
        ws = [S[j]["weight"]["kg"] for j in range(max(0, idx[ds] - 6), idx[ds] + 1) if S[j].get("weight") and S[j]["weight"].get("fasted") is not False]
        if not ws:   # weigh-ins are sparse: carry the last known fasted weight forward up to 21 days
            ws = [S[j]["weight"]["kg"] for j in range(idx[ds], max(-1, idx[ds] - 22), -1) if S[j].get("weight") and S[j]["weight"].get("fasted") is not False][:1]
        wkg = st.mean(ws) if ws else None
        im = x.get("intensity_min")
        sl = longevity._hrs(r.get("sleep"))
        onset = longevity._mins_from_noon(r["sleep_start"]) if r.get("sleep_start") else None
        prior = [longevity._mins_from_noon((det[S[j]["date"]].get("recovery") or {}).get("sleep_start")) for j in range(max(0, idx[ds] - 14), idx[ds])
                 if (det[S[j]["date"]].get("recovery") or {}).get("sleep_start")]
        f = {
            "steps": None if x.get("steps") is None else x["steps"] >= 7000,
            "aerobic": None if not im else (im.get("moderate", 0) + 2 * im.get("vigorous", 0)) >= 21,
            "strength": any(e.get("type") == "gym" for e in x.get("exercise") or []),
            "protein": None if not (t and wkg) else t["protein_g"] / wkg >= 1.6,
            "fibre": None if not t else t["fibre_g"] >= 30,
            "satfat": None if not (t and t["kcal"]) else 9 * t["satfat_g"] / t["kcal"] * 100 < 10,
            "sleep": None if sl is None else 7 <= sl <= 9,
            "bedtime": None if onset is None or len(prior) < 5 else abs(onset - st.median(prior)) <= 30,
        }
        out.append({"date": ds, **f})
    return out

def weekly(start, end):
    L = {m["id"]: m for m in longevity.compute()["markers"]}
    def at(key):   # latest rolling value within the week
        pts = [p for p in L[key]["history"] if start <= p[0][:10] <= end]
        return pts[-1][1] if pts else None
    rows = []
    for key, label in (("aerobic_min", "Aerobic minutes"), ("strength_sessions", "Strength sessions"), ("strength_min", "Strength minutes"),
                       ("steps", "Steps a day (30-day)"), ("protein_gkg", "Protein g/kg (7-day)"), ("fibre", "Fibre g/day (7-day)"),
                       ("satfat_pct", "Sat fat % energy (7-day)"), ("sleep_onset_sd", "Bedtime spread, min (14-day SD)")):
        m = L[key]; v = at(key)
        rows.append({"id": key, "label": label, "value": v, "unit": m["unit"], "status": longevity.status(m, v) if v is not None else "grey",
                     "green": m.get("green"), "amber": m.get("amber")})
    return rows
