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
    F = {"since": since, "days": days, "logged_days": logged_days, "recent_days": recent_days, "foods": rows,
         "sources": sources, "staples": staples,
         "counts": {"foods": len(rows), "week": sum(1 for r in rows if r["w_times"]), "new_this_month": sum(1 for r in rows if r["new_this_month"])}}
    F["plants"] = plants(); F["glucose"] = glucose_by_food(); F["slots"] = meal_slots(); F["weekdays"] = weekdays()
    F["swaps"] = swaps(F)
    return F


# ---------- extras: plants, glucose by food, meal slots, weekday pattern, swaps ----------

# Sections of the food files whose foods count as plants; other foods count if their name says so (oats, beans...).
PLANT_SECTIONS = {"veg", "fruit", "nuts"}
NO_NAME_MATCH = {"drinks", "mixed", "snacks"}   # a dish or a snack with tomato in it isn't a plant serving
# Matched anywhere in the name (blueberries, broccoli) or as whole words (oats, not "Nutrex"; rice, not "price").
PLANT_PARTS = ("berr", "brocc", "cauliflower", "mushroom", "avocado", "chickpea", "lentil", "quinoa", "buckwheat", "wholemeal",
               "wholegrain", "whole grain", "sourdough", "granola", "muesli", "edamame", "tempeh", "spinach")
PLANT_WORDS = ("oat", "rice", "bean", "tofu", "chia", "seed", "flax", "potato", "corn", "barley", "salad", "tomato", "banana",
               "apple", "guava", "kale", "carrot", "onion", "garlic", "pepper", "cabbage", "pea", "nut", "almond", "walnut",
               "cashew", "peanut", "veg", "vegetable", "fruit")
NOT_PLANT = ("milk", "tea", "coffee", "cake", "chip", "fries", "fried-rice", "biscuit", "digestive", "pudding", "ice-cream", "whey",
             "protein", "pizza", "juice", "oil", "cracker", "dessert", "garlic-bread", "sauce", "spring-roll", "yogurt")   # matched on the key
PLANT_GOAL = 30            # different plants a week, the American Gut Project's figure
SLOTS = ("breakfast", "lunch", "snacks", "dinner")
_sections = {}


def _section_map():
    """Food key -> the '# ---------- section ----------' it sits under in the starter and personal food files."""
    import re, nutrition
    out = {}
    for path in (nutrition.STARTER_PATH, nutrition.FOODS_PATH):
        try: text = path.read_text(encoding="utf-8")
        except OSError: continue
        sec = None
        for line in text.splitlines():
            m = re.match(r"#\s*-{3,}\s*(.+?)\s*-{3,}", line)
            if m: sec = m.group(1).split()[0].lower().strip("(&"); continue
            m = re.match(r"([a-z0-9][a-z0-9_-]*):", line)
            if m and sec: out[m.group(1)] = sec
    return out


def is_plant(key, f, sections):
    if "plant" in f: return bool(f["plant"])
    if any(w in key for w in NOT_PLANT): return False
    name = f"{key} {f.get('name') or ''}".lower().replace("-", " ")
    sec = sections.get(key)
    if sec in PLANT_SECTIONS: return True
    if sec in NO_NAME_MATCH: return False
    import re
    return (any(w in name for w in PLANT_PARTS)
            or bool(re.search(r"\b(" + "|".join(PLANT_WORDS) + r")(s|es)?\b", name)))


def _days():
    for p in data.day_files():
        d = data._jsonable(data._load(p))
        yield str(d.get("date")), d


def plants(weeks=8):
    """Different plants eaten in each of the last `weeks` 7-day blocks (the latest ends today)."""
    n = data._nutrition(); sec = _section_map()
    today = data.bkenv.today()
    blocks = [set() for _ in range(weeks)]
    for date, d in _days():
        back = (today - dt.date.fromisoformat(date)).days
        if not 0 <= back < 7 * weeks: continue
        for items in (d.get("meals") or {}).values():
            for it in items or []:
                for c in it.get("parsed") or []:
                    k = c.get("item"); f = n.FOODS.get(k)
                    if f and is_plant(k, f, sec): blocks[back // 7].add(k)
    names = lambda ks: sorted(((n.FOODS[k].get("name") or k.replace("-", " ")) for k in ks), key=str.lower)
    return {"goal": PLANT_GOAL, "this_week": len(blocks[0]), "plants": names(blocks[0]),
            "history": [{"end": (today - dt.timedelta(days=7 * i)).isoformat(), "count": len(b)} for i, b in enumerate(blocks)][::-1]}


def glucose_by_food(min_meals=2):
    """Median glucose rise after the meals each food was part of. A meal's rise is shared by everything in it."""
    import glucose
    if not glucose.RAW.exists(): return {"available": False}
    n = data._nutrition()
    rises = collections.defaultdict(list)
    for f in sorted(glucose.RAW.glob("*/*.json")):
        day = f.stem
        try: rs = glucose.readings(day)
        except Exception: continue
        if not rs: continue
        resp = [r for r in glucose.responses(day, rs) if not r.get("pending")]
        if not resp: continue
        p = data.day_file(day)
        if not p.exists(): continue
        d = data._jsonable(data._load(p))
        for meal, items in (d.get("meals") or {}).items():
            for it in items or []:
                t = str(it.get("time") or "")[:5]
                if not t: continue
                ev = [r for r in resp if r["time"] <= t and (dt.datetime.strptime(t, "%H:%M") - dt.datetime.strptime(r["time"], "%H:%M")).seconds <= 3600]
                if not ev: continue
                r = ev[-1]
                for c in it.get("parsed") or []:
                    k = c.get("item")
                    if k in n.FOODS and (day, r["time"]) not in {x[0] for x in rises[k]}:
                        rises[k].append(((day, r["time"]), r["rise"], r["peak"]))
    import statistics as stx
    rows = [{"key": k, "name": n.FOODS[k].get("name") or k.replace("-", " "), "meals": len(v),
             "rise": round(stx.median(x[1] for x in v), 1), "peak": round(stx.median(x[2] for x in v), 1),
             "max_rise": round(max(x[1] for x in v), 1)} for k, v in rises.items() if len(v) >= min_meals]
    rows.sort(key=lambda r: -r["rise"])
    return {"available": bool(rows), "foods": rows, "unit": "mmol/L"}


def meal_slots(days=28):
    """Per day, on average over complete days in the last `days`: what each meal slot supplies, and its top foods."""
    n = data._nutrition()
    since = (data.bkenv.today() - dt.timedelta(days=days)).isoformat()
    tot = {s: collections.Counter() for s in SLOTS}; top = {s: collections.Counter() for s in SLOTS}; ndays = 0
    for date, d in _days():
        if date < since or d.get("status") != "complete": continue
        ndays += 1
        for meal, items in (d.get("meals") or {}).items():
            s = meal if meal in tot else "snacks"
            for it in items or []:
                for c in it.get("parsed") or []:
                    if c.get("item") not in n.FOODS: continue
                    m = n.macros(c); tot[s].update({k: m.get(k, 0) for k in ("k", "p", "sf", "fib")}); top[s][c["item"]] += m.get("k", 0)
    if not ndays: return {"days": 0, "slots": []}
    return {"days": ndays, "slots": [{"slot": s, **{k: round(tot[s][k] / ndays, 1) for k in ("k", "p", "sf", "fib")},
             "top": [n.FOODS[k].get("name") or k.replace("-", " ") for k, _ in top[s].most_common(3)]} for s in SLOTS]}


def weekdays(days=56):
    """Average calories, protein, saturated fat and fibre by day of the week over complete days in the last `days`."""
    since = (data.bkenv.today() - dt.timedelta(days=days)).isoformat()
    by = collections.defaultdict(list)
    for d in data.summary():
        t = d.get("totals") or {}
        if d["date"] < since or d.get("status") != "complete" or not t.get("kcal"): continue
        by[dt.date.fromisoformat(d["date"]).weekday()].append(t)
    keys = (("kcal", "k"), ("protein_g", "p"), ("satfat_g", "sf"), ("fibre_g", "fib"))
    avg = lambda rows: {out: round(sum((r.get(src) or 0) for r in rows) / len(rows), 1) for src, out in keys} if rows else None
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    wk = [r for i in range(5) for r in by[i]]; we = [r for i in (5, 6) for r in by[i]]
    t = data.targets_for(data.bkenv.today().isoformat(), "rest")
    return {"targets": {"p": t.get("protein_min"), "sf": t.get("satfat_max"), "fib": t.get("fibre_min"), "k": t.get("kcal")},
            "days": [{"day": names[i], "n": len(by[i]), **(avg(by[i]) or {})} for i in range(7)],
            "weekday": avg(wk), "weekend": avg(we), "n_weekday": len(wk), "n_weekend": len(we)}


def swaps(F, lookback=90):
    """For the week's top saturated-fat sources: foods you already eat that give as much protein per calorie with far
    less saturated fat, and what swapping the week's calories of one for the other would have saved."""
    sec = _section_map()
    since = (data.bkenv.today() - dt.timedelta(days=lookback)).isoformat()
    def dens(r):
        p = r["per100"] or r["per_unit"]
        return (p["p"] / p["k"], p["sf"] / p["k"]) if p and p.get("k") else None
    pool = [r for r in F["foods"] if r["last"] >= since and r["times"] >= 2 and dens(r)]
    out = []
    for src in (F["sources"]["sf"]["top"] or [])[:3]:
        s = next((r for r in F["foods"] if r["key"] == src["key"]), None)
        ds = s and dens(s)
        if not ds or not ds[1]: continue
        kcal = (s["w_totals"] or {}).get("k", 0)
        cands, seen = [], set()
        for r in pool:
            dr = dens(r)
            if r["key"] == s["key"] or r["liquid"] != s["liquid"] or dr[1] > ds[1] * 0.5 or dr[0] < ds[0]: continue
            sig = (round(dr[0], 3), round(dr[1], 4))   # two entries with the same label figures (an old tub of the same yogurt)
            if sig in seen: continue
            seen.add(sig)
            cands.append({"key": r["key"], "name": r["name"], "saves_sf": round(kcal * (ds[1] - dr[1]), 1),
                          "protein_change": round(kcal * (dr[0] - ds[0]), 1), "same_kind": sec.get(r["key"]) == sec.get(s["key"])})
        cands.sort(key=lambda c: (not c["same_kind"], -c["saves_sf"]))
        out.append({"key": s["key"], "name": s["name"], "week_sf": src["value"], "week_kcal": round(kcal), "swaps": cands[:3]})
    return out
