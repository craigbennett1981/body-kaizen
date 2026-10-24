"""Resolve logged food text into foods.yaml items and compute macros.

resolve(raw, date) -> (components, problems)
  components: [{item, g|n|kcal, conf}]  conf: high | med | low
macros(component) -> dict of k p c f sf fib na caf
"""
import re, datetime as dt, pathlib, yaml
from fractions import Fraction

import bkenv
ROOT = bkenv.DATA
STARTER_PATH = bkenv.CODE / "foods" / "starter.yaml"   # shipped with the code
FOODS_PATH = ROOT / "foods.yaml"                         # your own foods, in your data folder: these win

def _y(p):
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}

FOODS = {**_y(STARTER_PATH), **(_y(FOODS_PATH) if FOODS_PATH.resolve() != STARTER_PATH.resolve() else {})}
OVERRIDES_PATH = ROOT / "overrides.yaml"
OVERRIDES = _y(OVERRIDES_PATH)
# eras: which food a generic name means on a given date (a change of brand), from settings.yaml, e.g.
#   eras: {milk-lowfat: [{from: 2026-10-20, use: milk-brand-b-lowfat}]}
ERAS = bkenv.settings().get("eras") or {}
KEYS = ["k", "p", "c", "f", "sf", "fib", "na", "caf"]

ALIASES = sorted(((a.lower(), key) for key, v in FOODS.items() for a in v.get("aliases", [])),
                 key=lambda t: -len(t[0]))

def to_ml(c):
    """Fluids are reported in ml: move a weight onto `ml` for liquid foods (1 g ~ 1 ml)."""
    if FOODS.get(c["item"], {}).get("liquid") and "g" in c:
        c["ml"] = c.pop("g")
    return c

def _date(d):
    return d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))

def era_key(key, date):
    """Follow settings.yaml `eras` rules: the first rule whose from/until window contains the date picks the food.
    Rules chain (tea-milk -> tea-lowfat -> tea-brand-b), up to a few steps."""
    date = _date(date)
    for _ in range(4):
        for r in ERAS.get(key) or []:
            if (r.get("from") is None or date >= _date(r["from"])) and (r.get("until") is None or date <= _date(r["until"])):
                key = r["use"]; break
        else:
            return key
    return key

def num(s):
    s = s.strip().lower()
    if s in ("half",): return 0.5
    if s in ("a", "one", ""): return 1.0
    return float(Fraction(s))

# compiled once: ~600 aliases overflow re's internal cache, so compiling per call made every lookup ~35 ms
_ALIAS_RX = [(re.compile(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])"), a, k) for a, k in ALIASES]

def match_food(text):
    t = " " + re.sub(r"[^a-z&' -]", " ", text.lower()) + " "
    t = re.sub(r"\s+", " ", t)
    best = None
    for rx, alias, key in _ALIAS_RX:
        m = rx.search(t)
        if m and (best is None or m.start() < best[0] or (m.start() == best[0] and len(alias) > len(best[2]))):
            best = (m.start(), key, alias)
    return (best[1], best[2]) if best else (None, None)

SCOOP_RE = re.compile(r"(\d+(?:/\d+)?|half|a|one)?\s*(?:scoop|scoops)\b(?:\s+of)?(?:\s+protei?n\s+powder)?", re.I)

def _part(part, date, problems):
    p = part.strip(" ,.-")
    if not p: return []
    low = p.lower()
    excluded = None
    ex_patterns = [r"\([^)]*?(?:bones?|bone weight|skin and bone|fat (?:mostly )?removed)\s*(\d+(?:\.\d+)?)\s*g?[^)]*\)?",
                   r"(?:bone and skin left|skin left|left)\s*(\d+(?:\.\d+)?)\s*g"]
    for pat in ex_patterns:
        m = re.search(pat, low)
        if m:
            excluded = float(m.group(1)); low = low[:m.start()] + " " + low[m.end():]; break
    raw_weight = bool(re.search(r"uncooked", low))
    low = re.sub(r"\(?uncooked weight\)?", " ", low)
    tb = re.search(r"(\d+)\s*(?:tablespoons?|tbsp)", low)
    if tb:
        low = low[:tb.start()] + f" {int(tb.group(1)) * 15}g " + low[tb.end():]
    kcal = re.search(r"(\d+(?:\.\d+)?)\s*(?:k?cals?|calories|kcal)\b", low)
    g = re.search(r"(\d+(?:\.\d+)?)\s*g\b", low)
    ml = re.search(r"(\d+(?:\.\d+)?)\s*ml\b", low)
    cnt = re.match(r"^(\d+(?:/\d+)?)\.?\s+(?!g\b|ml\b)", low)
    xn = re.search(r"\bx\s*(\d)\b", low)
    key, alias = match_food(low)
    if not key:
        problems.append(f"no food match: '{p}'"); return []
    key = era_key(key, date)
    if FOODS[key].get("era"):
        key = era_key(key, date)
    if key == "chia-soaked" and "dry" in low:
        key = "chia-dry"
    food = FOODS[key]
    comp = {"item": key}
    conf = "high"
    if kcal:
        comp["kcal"] = float(kcal.group(1)); conf = "med"
    elif g or ml:
        comp["g"] = float((g or ml).group(1))
    else:
        bare = [float(x) for x in re.findall(r"(?<![\d/])(\d+(?:\.\d+)?)(?![\d/]|\s*(?:x|%))", low)]
        n = None
        if cnt: n = num(cnt.group(1))
        elif xn: n = float(xn.group(1))
        if n is None and bare and food.get("by_kcal"):
            comp["kcal"] = bare[0]; conf = "med"
        elif n is None and bare and bare[0] < 10 and ("unit" in food or "unit_g" in food):
            comp["n"] = bare[0]
        elif n is not None and n >= 10:
            comp["g"] = n; n = None; conf = "med"
        elif n is None and bare and bare[0] >= 10 and "unit" not in food:
            comp["g"] = bare[0]; conf = "med"
        elif "g" in comp or "kcal" in comp or "n" in comp:
            pass
        elif n is not None:
            comp["n"] = n
        else:
            if "unit" in food or "unit_g" in food or "slice_g" in food:
                comp["n"] = 1.0
                if "unit" not in food: conf = "med"
            elif food.get("by_kcal"):
                problems.append(f"no kcal for '{p}'"); comp["g"] = 100.0; conf = "low"
            elif food.get("default_g"):
                comp["g"] = float(food["default_g"]); conf = "low"
            else:
                comp["g"] = 100.0; conf = "low"; problems.append(f"no amount, assumed 100g: '{p}'")
        if cnt and xn and "n" in comp: comp["n"] *= float(xn.group(1))
    if "cup" in low and key.startswith("yogurt"):
        comp.pop("n", None); comp["g"] = 150.0 * (num(cnt.group(1)) if cnt else 1); conf = "med"
    if "cup" in low and key == "apple-juice":
        comp.pop("n", None); comp["g"] = 250.0
    if excluded:
        comp["excluded_g"] = excluded
    elif "g" in comp and re.search(r"including bones?|incl\.? bone", low):
        comp["excluded_g"] = round(comp["g"] * 0.3); conf = "med"
    if key == "banana" and "g" in comp and "skin" in low:
        comp["g"] = round(comp["g"] * 0.65)
    if raw_weight:
        comp["raw_weight"] = True
    comp["conf"] = conf
    to_ml(comp)
    out = [comp]
    # bread + butter
    if re.search(r"(?:\band|\ban|&|\+)\s*(?:light\s+)?butter|light butter|light spread", low) and not re.search(r"no butter", low) and key in ("sourdough", "brown-bread"):
        slices = comp.get("n", 1.0) if "n" in comp else 1.0
        out.append({"item": "butter-light" if re.search(r"light", low) else "butter", "n": slices, "conf": "med"})
    return out

MEALS_PATH = ROOT / "meals.yaml"
MEALS = _y(MEALS_PATH)
MEAL_ALIASES = {a.lower(): k for k, v in MEALS.items() for a in [k, *(v.get("aliases") or [])]}

def resolve(raw, date):
    # named meal, optionally with a multiplier: "b1", "2x shake", "shake x2"
    m = re.fullmatch(r"\s*(?:(\d+(?:\.\d+)?)\s*x\s*)?(.+?)(?:\s*x\s*(\d+(?:\.\d+)?))?\s*", raw.lower())
    if m and m.group(2).strip() in MEAL_ALIASES:
        mult = float(m.group(1) or m.group(3) or 1)
        comps, probs = [], []
        for item in MEALS[MEAL_ALIASES[m.group(2).strip()]]["items"]:
            c_, p_ = resolve(item, date)
            for c in c_:
                c = dict(c)
                for k in ("g", "ml", "n", "kcal"):
                    if k in c: c[k] = round(c[k] * mult, 2)
                comps.append(c)
            probs += p_
        return comps, probs
    problems = []
    ov = OVERRIDES.get(raw.strip())
    if ov is not None:
        if isinstance(ov, dict) and "by_date" in ov:
            ov = ov["by_date"].get(str(date), ov.get("default", []))
        comps = []
        for c in ov:
            c = dict(c); c["item"] = era_key(c["item"], date); c.setdefault("conf", "med"); comps.append(to_ml(c))
        return comps, problems
    text = raw
    comps = []
    low = text.lower()
    # protein powder / shake
    if re.search(r"scoop|protein powder|protein shake|protein stake|protien powder", low):
        m = SCOOP_RE.search(text)
        if m:
            n = num(m.group(1) or "1"); text = text[:m.start()] + " " + text[m.end():]
        else:
            m2 = re.search(r"(\d+/\d+|half)\s*protein shake", low)
            n = num(m2.group(1)) if m2 else 1.0
        comps.append({"item": "scoop", "n": n, "conf": "high"})
        text = re.sub(r"(\d+/\d+\s*)?protei?n (powder|shake|stake)|protien powder|(?:and |with )water|and a\b|\bof\b", " ", text, flags=re.I)
    # creatine
    if re.search(r"creatine", text, re.I):
        text = re.sub(r"\d+\s*g\s*creatine|creatine\s*\d+\s*g|creatine", " ", text, flags=re.I)
        comps.append({"item": "creatine", "g": 0.0, "conf": "high"})
    HAS_AMT = r"\d+(?:\.\d+)?\s*(?:g|ml|k?cals?|calories)\b|^\s*\d"
    raw_parts = re.split(r"\s*\+\s*", text)
    parts = []
    for rp in raw_parts:
        sub = re.split(r",\s+", rp)
        if len(sub) > 1 and all(re.search(r"\d+\s*g\b", x) for x in sub):
            parts += sub
        else:
            parts.append(rp)
    # amount-less segment followed by a segment with an amount: weight belongs to the pair
    merged, carry = [], ""
    for i, part in enumerate(parts):
        part = (carry + " " + part).strip() if carry else part
        carry = ""
        if not re.search(HAS_AMT, part, re.I) and i + 1 < len(parts) and re.search(HAS_AMT, parts[i + 1], re.I):
            carry = part; continue
        merged.append(part)
    for part in merged:
        if not re.search(r"[a-z]{2,}", part, re.I): continue
        comps += _part(part, date, problems)
    return comps, problems

def macros(c):
    f = FOODS[c["item"]]
    out = dict.fromkeys(KEYS, 0.0)
    if "kcal" in c:
        base = f.get("per100") or f.get("unit")
        k = base.get("k") or 1
        scale = c["kcal"] / k
        for key in KEYS: out[key] = base.get(key, 0) * scale
        out["k"] = c["kcal"]
        return out
    if "g" in c or "ml" in c:
        g = c.get("g", c.get("ml")) - c.get("excluded_g", 0)
        if c.get("raw_weight") and f.get("raw_to_cooked"): g *= f["raw_to_cooked"]
        if "per100" in f:
            for key in KEYS: out[key] = f["per100"].get(key, 0) * g / 100
        else:
            ug = f.get("unit_g") or 100
            for key in KEYS: out[key] = f["unit"].get(key, 0) * g / ug
        return out
    n = c.get("n", 1.0)
    if "unit" in f:
        for key in KEYS: out[key] = f["unit"].get(key, 0) * n
    else:
        ug = f.get("unit_g") or f.get("slice_g") or f.get("default_g") or 100
        for key in KEYS: out[key] = f["per100"].get(key, 0) * ug * n / 100
    return out
