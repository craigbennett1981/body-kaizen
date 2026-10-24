"""Top-of-page summaries for the Day view: the one-line 'next move' and the readiness strip."""
import datetime as dt, json, statistics as st
import data


def _band(v):
    return (v[0], v[1]) if isinstance(v, (list, tuple)) else (v, v)

def _slot(minute):
    if minute < 10 * 60 + 30: return "Breakfast"
    if minute < 14 * 60: return "Lunch"
    if minute < 17 * 60: return "This afternoon"
    if minute < 21 * 60: return "Dinner"
    return "Before bed"

def next_move(date, now=None):
    det = data.day_detail(date)
    if not det: return None
    t, tot = det.get("targets") or {}, det.get("totals") or {}
    if not tot: return {"kind": "info", "text": "Nothing logged yet. Send breakfast when you've had it."}
    p, k, sf, fib = (tot.get(x) or 0 for x in ("protein_g", "kcal", "satfat_g", "fibre_g"))
    pmin, smax, fmin = t.get("protein_min"), t.get("satfat_max"), t.get("fibre_min")
    klo, khi = _band(t.get("kcal")) if t.get("kcal") else (None, None)
    if det.get("status") == "complete":
        hits, misses = [], []
        if pmin: (hits if p >= pmin else misses).append("protein" if p >= pmin else f"protein {pmin - p:.0f} g short")
        if smax: (hits if sf <= smax else misses).append("saturated fat" if sf <= smax else f"saturated fat {sf - smax:.1f} g over")
        if fmin: (hits if fib >= fmin else misses).append("fibre" if fib >= fmin else f"fibre {fmin - fib:.0f} g short")
        if klo: (hits if klo <= k <= khi else misses).append("calories" if klo <= k <= khi else f"calories {klo - k:.0f} under" if k < klo else f"calories {k - khi:.0f} over")
        text = "Day done." + (f" Hit {', '.join(hits)}." if hits else "") + (f" Missed: {'; '.join(misses)}." if misses else " Everything on target.")
        return {"kind": "bad" if any("saturated" in m for m in misses) else "good" if not misses else "warn", "text": text}
    now = now or data.bkenv.now()
    today = now.date().isoformat()
    minute = now.hour * 60 + now.minute if date == today else 24 * 60
    need_p = max(0, (pmin or 0) - p); need_k = max(0, (klo or 0) - k)
    sf_left = (smax - sf) if smax else None; fib_short = max(0, (fmin or 0) - fib)
    if date != today:
        gaps = [f"protein {need_p:.0f} g short" if need_p > 5 else "", f"fibre {fib_short:.0f} g short" if fib_short > 2 else "",
                f"saturated fat {-sf_left:.1f} g over" if sf_left is not None and sf_left < 0 else ""]
        gaps = [g for g in gaps if g]
        return {"kind": "warn" if gaps else "good", "text": "Not marked complete." + (f" As logged: {'; '.join(gaps)}." if gaps else " Targets met as logged.")}
    slot = _slot(minute)
    meals_left = 3 if minute < 10 * 60 else 2 if minute < 14 * 60 else 1.5 if minute < 17 * 60 else 1
    logged = {m for m, items in (det.get("meals") or {}).items() if items}
    if slot == "Breakfast" and "breakfast" in logged: slot, meals_left = "Lunch", 2
    if slot == "Lunch" and "lunch" in logged: slot, meals_left = "This afternoon", 1.5
    if slot == "Dinner" and "dinner" in logged: slot, meals_left = "Before bed", 1
    parts = []
    if need_p > 5:
        parts.append(f"aim for {need_p / meals_left:.0f} g protein" + (f" ({need_p:.0f} g still to go)" if meals_left > 1 else ""))
    if need_k > 100 and meals_left <= 1:
        parts.append(f"about {need_k:.0f} kcal")
    head = f"{slot}: " + " and ".join(parts) + "." if parts else ""
    tail = []
    if sf_left is not None:
        tail.append(f"Saturated fat is already {-sf_left:.1f} g over, so keep the rest of today lean." if sf_left < 0
                    else f"Only {sf_left:.1f} g saturated fat left." if sf_left < 8 else "")
    if fib_short > 5 and minute >= 12 * 60: tail.append(f"Fibre {fib_short:.0f} g short: add veg or fruit.")
    if det.get("day_type") in ("training", "big") and not det.get("exercise") and minute < 20 * 60:
        tail.append("Training day, but no session logged yet.")
    text = " ".join(x for x in [head] + tail if x)
    if not text: return {"kind": "good", "text": "On track: protein and calories covered. Nothing else needed today."}
    kind = "bad" if sf_left is not None and sf_left < 0 else "warn" if need_p > 40 and minute >= 14 * 60 else "info"
    return {"kind": kind, "text": text}

def _hrs(s):
    try: h, m = str(s).rstrip("m").split("h"); return int(h) + int(m) / 60
    except Exception: return None

def readiness(date):
    S = data.summary()
    idx = next((i for i, d in enumerate(S) if d["date"] == date), None)
    if idx is None: return None
    r = S[idx].get("recovery") or {}
    base = [b.get("recovery") or {} for b in S[max(0, idx - 28): idx]]
    def basel(k):
        v = [b.get(k) for b in base if isinstance(b.get(k), (int, float))]
        return round(st.mean(v)) if len(v) >= 7 else None
    out = {"sleep": r.get("sleep"), "sleep_h": _hrs(r.get("sleep")), "sleep_score": r.get("sleep_score"),
           "hrv": r.get("hrv_ms"), "hrv_base": basel("hrv_ms"), "hrv_status": r.get("hrv_status"),
           "rhr": r.get("rhr"), "rhr_base": basel("rhr"), "bb_charge": r.get("body_battery"), "bb_now": None}
    raw = data.ROOT / "imports" / "garmin" / date[:4] / f"{date}.json"
    try:
        s = json.loads(raw.read_text()).get("summary") or {}
        out["bb_now"] = s.get("bodyBatteryMostRecentValue")
    except Exception: pass
    try:
        import readiness as R
        sc = next((x for x in R.series() if x["date"] == date), None)
        if sc: out.update(score=sc["score"], band=sc["band"], drivers=sc["drivers"])
    except Exception: pass
    out["has_data"] = any(out.get(k) is not None for k in ("sleep", "hrv", "rhr", "bb_now"))
    return out

def build(date):
    return {"date": date, "move": next_move(date), "ready": readiness(date)}


def watch_upto():
    """Latest point Garmin has data for: the newest raw day's wellness end time (local, 'YYYY-MM-DDTHH:MM')."""
    raw_dir = data.ROOT / "imports" / "garmin"
    for f in sorted(raw_dir.glob("*/*.json"), reverse=True)[:3]:
        try: sm = json.loads(f.read_text()).get("summary") or {}
        except Exception: continue
        if sm.get("wellnessEndTimeLocal") and sm.get("totalKilocalories"): return sm["wellnessEndTimeLocal"][:16]
    return None
