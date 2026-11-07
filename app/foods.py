"""The Food tab: every food you've eaten, its macros, how much and how often, all time and in the last 7 days, and
which foods supplied the week's calories, protein, saturated fat and fibre."""
import datetime as dt, collections
import data

SOURCES = (("k", "Calories"), ("p", "Protein"), ("sf", "Saturated fat"), ("fib", "Fibre"))


def _per100(f):
    """Macros per 100 g (or ml): from per100, or scaled from a unit's macros and its weight."""
    if f.get("per100"): return {k: f["per100"].get(k, 0) for k in ("k", "p", "c", "f", "sf", "fib")}
    u, ug = f.get("unit") or {}, f.get("unit_g") or f.get("unit_ml") or f.get("cup_ml")
    if u and ug: return {k: round(u.get(k, 0) * 100 / ug, 1) for k in ("k", "p", "c", "f", "sf", "fib")}
    return None


def _per_unit(f):
    """For foods sized only by the serving (a cup of tea): macros per serving, so the table isn't blank."""
    u = f.get("unit") or {}
    return {k: u.get(k, 0) for k in ("k", "p", "c", "f", "sf", "fib")} if u and not _per100(f) else None


def _count(c, f):
    """How many servings an entry was, for foods logged by count (2 eggs). None when it was weighed."""
    if "g" in c or "ml" in c or not f.get("unit"): return None
    return c.get("n", 1.0)


def _amount(c, f):
    """How much of the food this entry was, in g (or ml for liquids). None if only a count with no unit weight."""
    if "g" in c or "ml" in c: return c.get("g", c.get("ml")) - c.get("excluded_g", 0)
    ug = f.get("unit_g") or f.get("unit_ml") or f.get("cup_ml") or f.get("slice_g") or f.get("default_g")
    return ug * c.get("n", 1.0) if ug else None


def build(days=7):
    n = data._nutrition()
    today = data.bkenv.today()
    since = (today - dt.timedelta(days=days - 1)).isoformat()
    month = today.replace(day=1).isoformat()
    foods = {}
    week = collections.defaultdict(lambda: collections.Counter())
    week_tot = collections.Counter()
    day_count, logged_days, recent_days = collections.Counter(), 0, 0
    for p in data.day_files():
        d = data._jsonable(data._load(p))
        date = str(d.get("date"))
        meals = d.get("meals") or {}
        seen_today = set()
        any_food = False
        for meal, items in meals.items():
            for it in items or []:
                for c in it.get("parsed") or []:
                    key = c.get("item")
                    if key not in n.FOODS: continue
                    any_food = True
                    f = n.FOODS[key]
                    m = n.macros(c)
                    amt = _amount(c, f); cnt = _count(c, f)
                    r = foods.setdefault(key, {"key": key, "name": f.get("name") or key.replace("-", " "), "liquid": bool(f.get("liquid")),
                                               "per100": _per100(f), "per_unit": _per_unit(f), "count": 0.0, "w_count": 0.0, "conf": f.get("conf"), "times": 0, "days": 0, "amount": 0.0,
                                               "totals": collections.Counter(), "first": date, "last": date,
                                               "w_times": 0, "w_amount": 0.0, "w_totals": collections.Counter(), "meals": collections.Counter()})
                    r["times"] += 1; r["amount"] += amt or 0; r["count"] += cnt or 0; r["totals"].update({k: v for k, v in m.items() if v})
                    r["first"] = min(r["first"], date); r["last"] = max(r["last"], date); r["meals"][meal] += 1
                    if key not in seen_today: r["days"] += 1; seen_today.add(key)
                    if date >= since:
                        r["w_times"] += 1; r["w_amount"] += amt or 0; r["w_count"] += cnt or 0; r["w_totals"].update({k: v for k, v in m.items() if v})
                        for k, _ in SOURCES: week[k][key] += m.get(k, 0); week_tot[k] += m.get(k, 0)
        if any_food:
            logged_days += 1
            if date >= since: recent_days += 1
    rows = []
    for r in foods.values():
        p100 = r["per100"] or r["per_unit"]
        rows.append({**{k: r[k] for k in ("key", "name", "liquid", "per100", "per_unit", "conf", "times", "days", "first", "last", "w_times")},
                     "amount": round(r["amount"]), "w_amount": round(r["w_amount"]),
                     "count": round(r["count"], 1), "w_count": round(r["w_count"], 1),
                     "totals": {k: round(v, 1) for k, v in r["totals"].items()},
                     "w_totals": {k: round(v, 1) for k, v in r["w_totals"].items()},
                     "protein_per_100kcal": round(p100["p"] * 100 / p100["k"], 1) if p100 and p100.get("k") else None,
                     "meal": r["meals"].most_common(1)[0][0] if r["meals"] else None,
                     "new_this_month": r["first"] >= month})
    rows.sort(key=lambda r: -r["times"])
    sources = {k: {"label": lab, "total": round(week_tot[k], 1),
                   "top": [{"key": f, "name": foods[f]["name"], "value": round(v, 1), "share": round(v / week_tot[k], 3) if week_tot[k] else 0}
                           for f, v in week[k].most_common(6) if v > 0]} for k, lab in SOURCES}
    staples = [{"key": r["key"], "name": r["name"], "days": r["days"], "share": round(r["days"] / logged_days, 2)}
               for r in sorted(rows, key=lambda r: -r["days"])[:8]] if logged_days else []
    return {"since": since, "days": days, "logged_days": logged_days, "recent_days": recent_days, "foods": rows,
            "sources": sources, "staples": staples,
            "counts": {"foods": len(rows), "week": sum(1 for r in rows if r["w_times"]), "new_this_month": sum(1 for r in rows if r["new_this_month"])}}
