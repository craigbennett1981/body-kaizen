#!/usr/bin/env python3
"""Resolve every food entry and (re)write parsed components + totals into day files.

usage: python3 scripts/compute.py [YYYY-MM-DD ...]   (no args = all days)
Idempotent: re-running after editing foods.yaml / overrides.yaml updates all numbers.
"""
import sys, pathlib, yaml, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import nutrition as N

ROOT = N.ROOT
TOTAL_KEYS = {"k": "kcal", "p": "protein_g", "c": "carbs_g", "f": "fat_g", "sf": "satfat_g",
              "fib": "fibre_g", "na": "sodium_mg", "caf": "caffeine_mg"}

def day_type(ex):
    types = [e.get("type") for e in ex or []]
    hard = [t for t in types if t in ("gym", "run", "swim", "ruck")]
    if not hard: return "rest"
    long_run = any(e.get("type") == "run" and (e.get("distance_km") or 0) >= 7 for e in ex)
    if ("gym" in types and "run" in types) or "ruck" in types or long_run or len(hard) >= 2:
        return "big"
    return "training"

def clean(c):
    out = {"item": c["item"]}
    for k in ("g", "ml", "n", "kcal", "excluded_g"):
        if k in c:
            v = c[k]; out[k] = int(v) if float(v).is_integer() else round(v, 2)
    if c.get("raw_weight"): out["raw_weight"] = True
    if c.get("conf", "high") != "high": out["conf"] = c["conf"]
    return out

def process(path):
    d = yaml.safe_load(path.read_text())
    tot = dict.fromkeys(TOTAL_KEYS, 0.0); low_k = 0.0; problems = []
    for meal, items in (d.get("meals") or {}).items():
        for it in items or []:
            if "raw" not in it: continue
            comps, probs = N.resolve(it["raw"], d["date"])
            problems += [f"{meal}: {p}" for p in probs]
            it["parsed"] = [clean(c) for c in comps]
            for c in comps:
                m = N.macros(c)
                for k in TOTAL_KEYS: tot[k] += m[k]
                if c.get("conf") == "low": low_k += m["k"]
    d["day_type"] = d.get("day_type_override") or day_type(d.get("exercise"))
    if any((d.get("meals") or {}).values()):
        t = {TOTAL_KEYS[k]: round(v) if k in ("k", "na", "caf") else round(v, 1) for k, v in tot.items()}
        t["low_confidence_kcal_pct"] = round(100 * low_k / tot["k"]) if tot["k"] else 0
        d["totals"] = t
    else:
        d.pop("totals", None)
    if problems: d["parse_problems"] = problems
    else: d.pop("parse_problems", None)
    # stable key order
    order = ["date", "status", "day_type", "notepad_label", "note", "weight", "recovery", "feel", "vitals",
             "environment", "steps", "exercise", "skipped_meals", "unknown_meals", "meals", "totals", "parse_problems"]
    d = {k: d[k] for k in order if k in d} | {k: v for k, v in d.items() if k not in order}
    path.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=None, width=200))
    return d

if __name__ == "__main__":
    files = sorted((ROOT / "days").rglob("*.yaml"))
    if len(sys.argv) > 1:
        want = set(sys.argv[1:]); files = [f for f in files if f.stem in want]
    for f in files:
        d = process(f)
        t = d.get("totals", {})
        print(f"{f.stem} {d['status']:9} {d['day_type']:8} kcal {t.get('kcal','-'):>5} P {t.get('protein_g','-'):>5} "
              f"SF {t.get('satfat_g','-'):>4} fib {t.get('fibre_g','-'):>4} low% {t.get('low_confidence_kcal_pct','-')}"
              + (f"  !! {d['parse_problems']}" if d.get("parse_problems") else ""))
