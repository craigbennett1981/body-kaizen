"""Load watch: how the last days of training compare with your own usual, stated as numbers, not as a judgement.

Five signals, each against your own trailing 12 weeks: training days in a row, rest days in the last 7, minutes in
heart-rate zone 4 and above over 12 days, weeks since a lighter week, and two days running eaten well under burn.
When off episodes are recorded (measurements/episodes.yaml, or days with symptoms), it also counts how often the
signals were raised the day before one, next to how often they are raised on ordinary days. It reports; it does
not diagnose or prescribe.
"""
import datetime as dt, statistics as st
import data

WINDOW = 12          # days of hard minutes
HISTORY = 84         # days of "your usual"
SHORT_KCAL = 250     # eaten this far under burn counts as a short day
NEED = 2             # signals raised before the Day tab mentions it

_cache = {}


def _d(s): return dt.date.fromisoformat(str(s)[:10])


def _series():
    """Per calendar day, oldest first: trained, zone 4+ minutes, session kcal, and eaten minus burn (complete days)."""
    S = data.summary()
    if not S: return [], {}
    key = (str(data.ROOT), len(S), S[-1]["date"], sum(len(d.get("exercise") or []) for d in S[-14:]), (S[-1].get("totals") or {}).get("kcal"))
    if key in _cache: return _cache[key]
    by = {d["date"]: d for d in S}
    try:
        import zones
        Z = {z["date"]: (z.get("z4") or 0) + (z.get("z5") or 0) for z in zones.build()["days"]}
    except Exception: Z = {}
    E = {d["date"]: d for d in data.energy()["days"]}
    try:
        import energybalance
        f = energybalance._scale_factor() or 1.0
    except Exception: f = 1.0
    out, d, end = [], _d(S[0]["date"]), _d(S[-1]["date"])
    while d <= end:
        ds = d.isoformat(); x = by.get(ds) or {}
        ex = [e for e in x.get("exercise") or [] if e.get("type") != "walk"]
        k, b = (x.get("totals") or {}).get("kcal"), x.get("burn")
        out.append({"date": ds, "trained": bool(ex), "hard": Z.get(ds, 0),
                    "kcal": sum(s["kcal"] for s in (E.get(ds) or {}).get("sessions", []) if s["type"] != "walk"),
                    "bal": round(k - b * f) if k and b and x.get("status") == "complete" else None,
                    "symptoms": bool(x.get("symptoms"))})
        d += dt.timedelta(days=1)
    _cache.clear(); _cache[key] = (out, {r["date"]: i for i, r in enumerate(out)})
    return _cache[key]


def _streak(T, i):
    n = 0
    while i - n >= 0 and T[i - n]["trained"]: n += 1
    return n


def _at(T, i):
    """The five signals as of day i (inclusive)."""
    lo = max(0, i - WINDOW - HISTORY + 1); past = range(lo + WINDOW, i - WINDOW + 1)   # earlier days, clear of this window
    sig = []
    # 1. training days in a row
    s = _streak(T, i); prev = max((_streak(T, j) for j in past), default=None)
    sig.append({"id": "streak", "value": s, "usual": prev, "flag": s >= 4 and prev is not None and s > prev,
                "text": f"{s} training days in a row" + (f" (longest in the {HISTORY // 7} weeks before: {prev})" if prev is not None else "")})
    # 2. rest days in the last 7
    rest = lambda j: sum(1 for x in T[max(0, j - 6): j + 1] if not x["trained"])
    r = rest(i); usual = st.median([rest(j) for j in past]) if len(past) >= 14 else None
    sig.append({"id": "rest", "value": r, "usual": usual, "flag": i >= 6 and r <= 1 and usual is not None and r < usual,
                "text": f"{r} rest day{'s' if r != 1 else ''} in the last 7" + (f" (usual: {usual:g})" if usual is not None else "")})
    # 3. minutes in zone 4 and above
    hard = lambda j: sum(x["hard"] for x in T[max(0, j - WINDOW + 1): j + 1])
    h = hard(i); usual = st.median([hard(j) for j in past]) if len(past) >= 14 else None
    sig.append({"id": "hard", "value": h, "usual": usual, "flag": usual is not None and h >= 40 and h >= 2 * max(usual, 1),
                "text": f"{h} min in heart-rate zone 4 and above over {WINDOW} days" + (f" (usual: {usual:g})" if usual is not None else "")})
    # 4. weeks since a lighter week: a 7-day session burn at or under 70% of the three weeks before it
    load = lambda j: sum(x["kcal"] for x in T[max(0, j - 6): j + 1])
    since = None
    for j in range(i, 27, -1):
        base = (load(j - 7) + load(j - 14) + load(j - 21)) / 3
        if base > 300 and load(j) <= 0.7 * base: since = i - j; break
    weeks = None if since is None and i < 48 else (since // 7 if since is not None else (i - 27) // 7)
    sig.append({"id": "light", "value": weeks, "usual": None, "flag": weeks is not None and weeks >= 4,
                "text": (f"{weeks} week{'s' if weeks != 1 else ''} since a lighter week" + ("" if since is not None else " or more")) if weeks is not None else "not enough history for lighter weeks"})
    # 5. two days running eaten well under burn (Garmin's burn scaled by real maintenance)
    b = [T[j]["bal"] for j in (i - 1, i) if j >= 0]
    two = len(b) == 2 and all(v is not None and v < -SHORT_KCAL for v in b)
    sig.append({"id": "fuel", "value": b if two else None, "usual": None, "flag": two,
                "text": f"eaten {-b[0]} and {-b[1]} kcal under burn on the last two days" if two else "no two short days running"})
    return sig


def _episodes(T, idx):
    """Start dates of off episodes: the recorded ones, plus the first day of any run of days with symptoms."""
    try:
        import readiness
        starts = {e["start"] for e in readiness.episodes()}
    except Exception: starts = set()
    for i, x in enumerate(T):
        if x["symptoms"] and not (i and T[i - 1]["symptoms"]): starts.add(x["date"])
    starts = sorted(s for s in starts if s in idx)
    return [s for k, s in enumerate(starts) if not k or (_d(s) - _d(starts[k - 1])).days > 3]   # one episode, not two


def build(date=None):
    T, idx = _series()
    today = data.bkenv.today().isoformat()
    date = date or today
    if not T or date not in idx: return {"date": date, "available": False}
    i = idx[date]
    if date == today and not T[i]["trained"] and i: i -= 1   # today so far: judged as of last night
    if i < WINDOW: return {"date": date, "available": False}
    sig = _at(T, i); raised = [s for s in sig if s["flag"]]
    out = {"date": date, "as_of": T[i]["date"], "available": True, "signals": sig, "raised": len(raised), "show": len(raised) >= NEED}
    # how the same count has gone before: the day before each episode, and ordinary days
    first = 2 * WINDOW + 14   # the first day with enough history behind it for "your usual"
    eps = [e for e in _episodes(T, idx) if idx[e] - 1 >= first and e <= T[i]["date"]]
    count = lambda j: sum(1 for s in _at(T, j) if s["flag"])
    if eps and raised:
        n = len(raised)
        near = set()
        for e in eps: near.update(range(idx[e] - 3, idx[e] + 6))
        before = sum(1 for e in eps if count(idx[e] - 1) >= n)
        ordinary = [j for j in range(first, i + 1) if j not in near]
        pct = round(100 * sum(1 for j in ordinary if count(j) >= n) / len(ordinary)) if len(ordinary) >= 28 else None
        out["history"] = {"episodes": len(eps), "raised_before": before, "ordinary_pct": pct, "at_least": n}
    if raised:
        t = "; ".join(s["text"] for s in raised)
        t = t[0].upper() + t[1:] + "."
        h = out.get("history")
        if h and h["ordinary_pct"] is not None:
            t += (f" The day before {h['raised_before']} of your {h['episodes']} recorded off episodes, at least {h['at_least']} of these were raised;"
                  f" on ordinary days that is the case {h['ordinary_pct']}% of the time.")
        out["text"] = t
    return out
