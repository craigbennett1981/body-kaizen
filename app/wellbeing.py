"""Mood and health issues you report: daily feel scores (1–5) and symptoms, with context from sleep and episodes."""
import datetime as dt, statistics as st
from collections import defaultdict
import data, longevity

SCORES = ["overall", "mood", "energy", "gut", "stress"]
SEV = {"mild": 1, "moderate": 2, "severe": 3}

def _hrs(s):
    try: h, m = str(s).replace("m", "").split("h"); return int(h) + int(m) / 60
    except Exception: return None

def _sev(v):
    if isinstance(v, str): return SEV.get(v.lower(), 1)
    return int(v or 1)

def compute():
    S = data.summary()
    days = []
    for p in data.day_files():
        d = data._jsonable(data._load(p))
        feel = d.get("feel") or {}
        sym = [{"what": str(s.get("what", "")).replace("_", "-"), "severity": _sev(s.get("severity")), **{k: s[k] for k in ("time", "note", "area") if s.get(k)}}
               for s in (d.get("symptoms") or []) if s.get("what")]
        for t in feel.get("tags") or []:   # older shorthand: feel tags were symptoms
            sym.append({"what": str(t), "severity": 1})
        days.append({"date": d["date"], "feel": {k: feel.get(k) for k in SCORES if feel.get(k) is not None},
                     "note": feel.get("note"), "symptoms": sym,
                     "sleep_h": _hrs((d.get("recovery") or {}).get("sleep")), "trained": bool(d.get("exercise"))})
    today = dt.date.fromisoformat(days[-1]["date"]) if days else data.bkenv.today()
    ago = lambda d: (today - dt.date.fromisoformat(d["date"])).days
    rep = [d for d in days if d["feel"] or d["symptoms"]]
    # 7-day averages vs the 28 days before
    def avg(k, lo, hi):
        v = [d["feel"][k] for d in days if k in d["feel"] and lo <= ago(d) < hi]
        return round(st.mean(v), 1) if v else None
    summary = {k: {"now": avg(k, 0, 7), "before": avg(k, 7, 35)} for k in SCORES}
    # symptom counts and simple context
    by = defaultdict(list)
    for i, d in enumerate(days):
        for s in d["symptoms"]: by[s["what"]].append((i, s))
    sleep_all = [d["sleep_h"] for d in days if d["sleep_h"]]
    base_sleep = st.mean(sleep_all) if sleep_all else None
    sym = []
    for what, occ in sorted(by.items(), key=lambda x: -len(x[1])):
        dates = [days[i]["date"] for i, _ in occ]
        sl = [days[i]["sleep_h"] for i, _ in occ if days[i]["sleep_h"]]
        ctx = None
        if len(occ) >= 3 and sl and base_sleep:
            ctx = f"Sleep on those nights averaged {st.mean(sl):.1f} h vs {base_sleep:.1f} h overall."
        sym.append({"what": what, "count": len(occ), "count_30d": sum(1 for i, _ in occ if ago(days[i]) < 30),
                    "last": dates[-1], "max_severity": max(s["severity"] for _, s in occ), "dates": dates, "context": ctx})
    eps = [{"start": str(e["start"])[:10], "end": str(e.get("end") or e["start"])[:10], "what": e.get("what")} for e in longevity._yaml("episodes.yaml")]
    return {"as_of": days[-1]["date"] if days else None, "days": days[-120:], "reports": list(reversed(rep))[:40],
            "summary": summary, "symptoms": sym, "episodes": eps,
            "logged_14d": sum(1 for d in days if ago(d) < 14 and d["feel"]), "symptom_days_30d": sum(1 for d in days if ago(d) < 30 and d["symptoms"])}
