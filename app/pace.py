"""Pace through the day: split each daily macro target into windows (before lunch, lunch to dinner,
dinner and after) and judge how on-track the day is right now, not just against the full-day total."""
import datetime as dt
import data

KEYS = {"kcal": ("kcal", "range"), "carbs_g": ("carbs", "range"), "fat_g": ("fat", "range"), "protein_g": ("protein_min", "min"), "fibre_g": ("fibre_min", "min"), "satfat_g": ("satfat_max", "max")}
MK = {"kcal": "k", "carbs_g": "c", "fat_g": "f", "protein_g": "p", "fibre_g": "fib", "satfat_g": "sf"}
MEAL_WIN = {"breakfast": 0, "lunch": 1, "dinner": 2}

def _min(s):
    h, m = str(s)[:5].split(":"); return int(h) * 60 + int(m)

def _cfg():
    return data._targets_file().get("pace") or {}

def build(date, now=None):
    det = data.day_detail(date)
    cfg = _cfg()
    if not det or not cfg: return None
    t = det.get("targets") or {}
    wins = cfg["windows"]; ends = [_min(w["until"]) for w in wins]; starts = [_min(cfg.get("start", "07:00"))] + ends[:-1]
    n = len(wins)
    # what was eaten in each window
    eaten = {k: [0.0] * n for k in KEYS}; untimed = 0
    for meal, items in (det.get("meals") or {}).items():
        for it in items or []:
            if it.get("time"):
                m = _min(it["time"]); i = next((j for j, e in enumerate(ends) if m < e), n - 1)
            elif meal in MEAL_WIN: i = MEAL_WIN[meal]
            else: untimed += 1; continue
            for c in it.get("parsed") or []:
                for k in KEYS: eaten[k][i] += (c.get("macros") or {}).get(MK[k]) or 0
    if isinstance(now, str):   # "HH:MM" on that date
        now = dt.datetime.combine(dt.date.fromisoformat(date), dt.time.fromisoformat(now), data.bkenv.tz())
    now = now or data.bkenv.now()
    complete = det.get("status") == "complete"
    nowm = now.hour * 60 + now.minute if (date == now.date().isoformat() and not complete) else 24 * 60
    cur = next((j for j, e in enumerate(ends) if nowm < e), n)   # index of the window we're in (n = all done)
    frac = 0 if cur >= n else max(0.0, min(1.0, (nowm - starts[cur]) / (ends[cur] - starts[cur])))
    on, behind = cfg.get("on_pace", 0.85), cfg.get("behind", 0.65)
    out = {"windows": [{"name": w["name"], "from": f"{starts[i]//60:02d}:{starts[i]%60:02d}", "until": w["until"],
                        "state": "done" if i < cur else "now" if i == cur else "later"} for i, w in enumerate(wins)],
           "now": f"{min(nowm, 1439)//60:02d}:{min(nowm, 1439)%60:02d}", "complete": complete or cur >= n, "untimed": untimed, "macros": {}}
    for k, (tk, kind) in KEYS.items():
        v = t.get(tk)
        if v is None: continue
        lo, hi = (v[0], v[1]) if isinstance(v, (list, tuple)) else (v, v)
        sh = cfg.get("share") or {}
        share = sh.get(k) or sh.get("kcal") or [1 / n] * n   # carbs and fat follow the calorie split
        cum_share = sum(share[:cur]) + (share[cur] * frac if cur < n else 0)
        got = sum(eaten[k])
        exp_lo, exp_hi = lo * cum_share, hi * cum_share
        # status: floors need enough eaten by now; caps must not be exceeded by now; a calorie range checks both
        if cum_share <= 0: status = "none"
        elif kind == "max":
            status = "good" if got <= exp_hi * 1.05 else "warn" if got <= exp_hi * 1.25 else "bad"
            if got > hi: status = "bad"
        else:
            r = got / exp_lo if exp_lo else 1
            status = "good" if r >= on else "warn" if r >= behind else "bad"
            if kind == "range" and got > exp_hi * 1.15: status = "warn" if got <= hi else "bad"
        # per-window plan: finished windows keep their original share; what's left is spread over the rest
        wins_out = []
        left_lo = lo - sum(eaten[k][:cur]); left_share = sum(share[cur:]) or 1
        for i in range(n):
            plan = lo * share[i] if i < cur else max(0.0, left_lo) * share[i] / left_share
            if kind == "max": plan = hi * share[i] if i < cur else max(0.0, hi - sum(eaten[k][:cur])) * share[i] / left_share
            if i < cur:
                a = eaten[k][i]
                ws = ("good" if a <= plan * 1.1 else "warn" if a <= plan * 1.3 else "bad") if kind == "max" else \
                     ("good" if a >= plan * on else "warn" if a >= plan * behind else "bad")
            else: ws = "now" if i == cur else "later"
            wins_out.append({"eaten": round(eaten[k][i], 1), "plan": round(plan, 1), "state": ws})
        out["macros"][k] = {"eaten": round(got, 1), "expected": round(exp_lo if kind != "max" else exp_hi, 1),
                            "kind": kind, "status": status, "windows": wins_out}
    return out
