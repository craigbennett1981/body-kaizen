"""Heart-rate zone balance: minutes in each of Garmin's five zones per day, from every workout with watch data, and
how easy your easy runs really are.

The page adds the days up into days, weeks or months to match the Training period. Zones 1-2 count as easy and 3-5
as hard: a five-zone simplification of the 80/20 pattern endurance athletes train to (about 80% of the time easy).
An easy run is one logged with `effort: easy`; it should average under targets.yaml reference.easy_run_avg_hr_max.
"""
import data

EASY_SHARE = 0.8    # the 80/20 line
ZONES = ("z1", "z2", "z3", "z4", "z5")


def build():
    days, runs = {}, []
    cap = (data.reference() or {}).get("easy_run_avg_hr_max", 140)
    for p in data.day_files():
        d = data._jsonable(data._load(p))
        for e in d.get("exercise") or []:
            z = e.get("zones_min") or {}
            if not any(z.get(k) for k in ZONES): continue
            row = days.setdefault(d["date"], {"date": d["date"], **{k: 0 for k in ZONES}, "sessions": 0})
            for k in ZONES: row[k] += int(z.get(k) or 0)
            row["sessions"] += 1
            if e.get("type") == "run":
                tot = sum(int(z.get(k) or 0) for k in ZONES)
                hr = (e.get("hr") or {}).get("avg")
                runs.append({"date": d["date"], "effort": e.get("effort"), "hr_avg": hr, "minutes": tot,
                             "easy_min": int(z.get("z1") or 0) + int(z.get("z2") or 0),
                             "under_cap": hr <= cap if isinstance(hr, (int, float)) else None})
    return {"days": sorted(days.values(), key=lambda r: r["date"]), "runs": runs, "easy_cap": cap, "easy_share": EASY_SHARE}
