#!/usr/bin/env python3
"""Pull Garmin Connect data into the day files, then commit and push.

  .venv/bin/python scripts/garmin_pull.py              # last 3 days (default; what the scheduler runs)
  .venv/bin/python scripts/garmin_pull.py --since 2026-07-24   # backfill history
  .venv/bin/python scripts/garmin_pull.py --remap      # re-apply saved raw files after a mapping fix (no network)
  add --no-git to skip commit/push

Raw responses are kept in imports/garmin/YYYY/YYYY-MM-DD.json, so mapping bugs never lose data.
"""
import argparse, datetime as dt, json, os, pathlib, subprocess, sys, time, traceback
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bkenv  # noqa: E402
ROOT = bkenv.DATA
import garmin_map as M   # noqa: E402
import compute           # noqa: E402

RAW = ROOT / "imports" / "garmin"
STATE = RAW / "state.json"
TOKENS = str(pathlib.Path("~/.garminconnect").expanduser())
TODAY = lambda: bkenv.now().date()

def log(*a): print(bkenv.now().strftime("%H:%M:%S"), *a, flush=True)

def load_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def save_state(**kw):
    s = load_state(); s.update(kw); RAW.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2, default=str))

def connect():
    from garminconnect import Garmin
    api = Garmin()
    api.login(TOKENS)   # reuses ~/.garminconnect; raises if the token is missing/expired -> run garmin_login.py
    return api

WARN = []   # (date, part, error) for calls that failed

def _safe(fn, *a):
    try: return fn(*a)
    except Exception as e:
        log(f"  {fn.__name__} failed: {type(e).__name__}: {e}")
        WARN.append((a[0] if a else "", fn.__name__.replace("get_", "").replace("_data", "").replace("_by_date", ""), f"{type(e).__name__}: {e}"[:160]))
        return None

# Never keep anything that locates or identifies the person in the saved raw files (they go to GitHub).
SCRUB = ("latitude", "longitude", "polyline", "location", "geo", "owner", "displayname", "fullname",
         "profileimage", "userprofile", "email", "address", "city", "country", "timezoneid")

def scrub(o):
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items() if not any(t in k.lower() for t in SCRUB)}
    if isinstance(o, list):
        return [scrub(x) for x in o]
    return o

def fetch_day(api, d):
    ds = d.isoformat()
    raw = {"date": ds, "fetched_at": bkenv.now().isoformat(timespec="seconds"),
           "summary": _safe(api.get_user_summary, ds),
           "sleep": _safe(api.get_sleep_data, ds),
           "hrv": _safe(api.get_hrv_data, ds),
           "activities": _safe(api.get_activities_by_date, ds, ds) or []}
    raw.update(fetch_intraday(api, ds))
    p = RAW / ds[:4] / f"{ds}.json"; p.parent.mkdir(parents=True, exist_ok=True)
    raw = scrub(raw)
    p.write_text(json.dumps(raw, indent=1, default=str))
    return raw, p

def fetch_intraday(api, ds):
    """Compact intraday series for the Day timeline: 15-min steps and body battery / stress (epoch ms, value)."""
    out = {}
    if hasattr(api, "get_steps_data"):
        st = _safe(api.get_steps_data, ds)
        if isinstance(st, list):
            out["steps_intraday"] = [[x.get("startGMT"), x.get("steps") or 0] for x in st if isinstance(x, dict) and x.get("startGMT")]
    if hasattr(api, "get_stress_data"):
        sd = _safe(api.get_stress_data, ds)
        if isinstance(sd, dict):
            bb = []
            for row in sd.get("bodyBatteryValuesArray") or []:
                if not isinstance(row, list) or len(row) < 2: continue
                lvl = row[2] if len(row) >= 3 and isinstance(row[1], str) else row[1]
                if isinstance(lvl, (int, float)): bb.append([row[0], lvl])
            out["body_battery_intraday"] = bb
            out["stress_intraday"] = [[r[0], r[1]] for r in sd.get("stressValuesArray") or [] if isinstance(r, list) and len(r) >= 2 and isinstance(r[1], (int, float)) and r[1] >= 0]
    return out

ACT = RAW / "activities"

def _activity_summary(api, aid):
    """Fields only the single-activity endpoint has, e.g. the watch's recovery heart rate (HR drop after stopping)."""
    if not hasattr(api, "get_activity"): return {}
    full = _safe(api.get_activity, aid)
    sm = (full or {}).get("summaryDTO") or {} if isinstance(full, dict) else {}
    keep = {k: v for k, v in sm.items() if any(t in k.lower() for t in ("recovery", "minhr", "maxhr", "averagehr", "lactate", "trainingload", "activitytrainingload"))}
    return keep

def fetch_activity_detail(api, a):
    """HR (and speed) trace for one activity, saved once to imports/garmin/activities/<id>.json."""
    aid = (a or {}).get("activityId")
    if not aid or not hasattr(api, "get_activity_details"): return None
    p = ACT / f"{aid}.json"
    if p.exists():
        cur = json.loads(p.read_text())
        if "summary" in cur: return p
        cur["summary"] = _activity_summary(api, aid)   # added later: fetch it once for older files
        p.write_text(json.dumps(cur, separators=(",", ":"))); return p
    det = _safe(api.get_activity_details, aid)
    if not isinstance(det, dict): return None
    idx = {m.get("key"): m.get("metricsIndex") for m in det.get("metricDescriptors") or []}
    ti, hi, si = idx.get("directTimestamp"), idx.get("directHeartRate"), idx.get("directSpeed")
    pts = []
    for row in det.get("activityDetailMetrics") or []:
        m = row.get("metrics") or []
        try: t = m[ti]
        except Exception: continue
        hr = m[hi] if hi is not None and hi < len(m) else None
        sp = m[si] if si is not None and si < len(m) else None
        if t is None or hr is None: continue
        pts.append([int(t), round(hr), round(sp, 2) if isinstance(sp, (int, float)) else None])
    if not pts: return None
    out = {"activity_id": aid, "type": (a.get("activityType") or {}).get("typeKey"), "start_local": a.get("startTimeLocal"),
           "start_gmt": a.get("startTimeGMT"), "duration_s": a.get("duration"), "samples": pts,
           "aerobic_te": a.get("aerobicTrainingEffect"), "anaerobic_te": a.get("anaerobicTrainingEffect"),
           "te_label": a.get("trainingEffectLabel"), "body_battery_change": a.get("differenceBodyBattery"),
           "summary": _activity_summary(api, aid)}
    ACT.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(out, separators=(",", ":")))
    return p

VO2 = RAW / "vo2max.json"

def fetch_vo2(api, start, end):
    """VO2max/fitness age history for the range, merged into imports/garmin/vo2max.json {date: {...}}."""
    have = json.loads(VO2.read_text()) if VO2.exists() else {}
    res = _safe(api.get_max_metrics_range, start.isoformat(), end.isoformat()) or []
    for item in res if isinstance(res, list) else [res]:
        g = (item or {}).get("generic") or {}
        d = g.get("calendarDate")
        v = g.get("vo2MaxPreciseValue") or g.get("vo2MaxValue")
        if d and v: have[d] = {"vo2max": round(float(v), 1), **({"fitness_age": g["fitnessAge"]} if g.get("fitnessAge") else {})}
    RAW.mkdir(parents=True, exist_ok=True); VO2.write_text(json.dumps(have, indent=1, sort_keys=True))
    return have

FAGE = RAW / "fitness_age.json"

def fetch_fitness_age(api, d):
    """Garmin Fitness Age for a date, merged into imports/garmin/fitness_age.json {date: {...}}."""
    have = json.loads(FAGE.read_text()) if FAGE.exists() else {}
    res = _safe(api.get_fitnessage_data, d.isoformat()) if hasattr(api, "get_fitnessage_data") else None
    if not isinstance(res, dict) or not res: return have
    keep = {k: res[k] for k in ("chronologicalAge", "fitnessAge", "achievableFitnessAge", "previousFitnessAge", "lastUpdated") if res.get(k) is not None}
    comps = res.get("components") or {}
    if comps: keep["components"] = {k: {kk: v.get(kk) for kk in ("value", "targetValue", "improvementValue") if isinstance(v, dict) and v.get(kk) is not None}
                                    for k, v in comps.items()}
    if keep.get("fitnessAge") is not None:
        have[d.isoformat()] = keep
        RAW.mkdir(parents=True, exist_ok=True); FAGE.write_text(json.dumps(have, indent=1, sort_keys=True))
    return have

def day_path(d):
    return ROOT / "days" / str(d.year) / f"{d.isoformat()}.yaml"

def apply(d, raw):
    """Merge one day's raw Garmin data into its day file (creating it if needed). Returns (path, changes)."""
    p = day_path(d); p.parent.mkdir(parents=True, exist_ok=True)
    day = yaml.safe_load(p.read_text()) if p.exists() else {"date": d, "status": "unlogged",
                                                           "meals": {"breakfast": [], "lunch": [], "dinner": [], "snacks": []}}
    mapped = M.map_day(raw)
    vo2 = (json.loads(VO2.read_text()) if VO2.exists() else {}).get(d.isoformat())
    if vo2: mapped["fitness"] = vo2
    changes = M.merge_day(day, mapped)
    if changes or not p.exists():
        p.write_text(yaml.safe_dump(day, sort_keys=False, allow_unicode=True, default_flow_style=None, width=200))
        compute.process(p)
    return p, changes

def git(*args, check=True):
    for attempt in range(6):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=90)
        if r.returncode == 0 or "index.lock" not in (r.stderr or ""): break
        time.sleep(2)   # another commit (e.g. from chat) holds the lock
    if check and r.returncode != 0: raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r

def commit_and_push(paths, summary, prefix="garmin"):
    """Commit changed data files to the data folder's git repo, and push only if settings.yaml says so:
    git: {auto_commit: true, auto_push: false} are the defaults. Returns True/False for a push, None if not pushed."""
    opts = bkenv.git_options()
    if not opts["auto_commit"]: return None
    if git("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        log("data folder isn't a git repository: not committing"); return None
    rel = [str(pathlib.Path(p).relative_to(ROOT)) for p in paths]
    git("add", "--", *rel)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        log("nothing new to commit")
    else:
        git("commit", "-m", f"{prefix}: {summary}", "--", *rel)
        log("committed")
    if not opts["auto_push"]: return None   # push yourself, or set git.auto_push: true in settings.yaml
    r = git("push", "origin", "HEAD", check=False)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode == 0 or out.endswith("Everything up-to-date"):
        log("pushed" if "up-to-date" not in out else "already up to date on GitHub"); return True
    log(f"push failed (exit {r.returncode}, will retry next run):\n{out}")
    save_state(last_push_error=out[-600:])
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="pull this many days back including today (default 3)")
    ap.add_argument("--since", help="pull every day from this date (YYYY-MM-DD) to today")
    ap.add_argument("--remap", action="store_true", help="re-apply saved raw files only, no network")
    ap.add_argument("--no-git", action="store_true")
    a = ap.parse_args()
    today = TODAY()
    start = dt.date.fromisoformat(a.since) if a.since else today - dt.timedelta(days=a.days - 1)
    dates = [start + dt.timedelta(days=i) for i in range((today - start).days + 1)]
    save_state(last_attempt=bkenv.now().isoformat(timespec="seconds"))
    touched, summary = [], []
    try:
        api = None if a.remap else connect()
        if api:
            first = bkenv.start_date() if not VO2.exists() else dates[0]   # first run fetches full history in one call
            fetch_vo2(api, first, dates[-1]); touched.append(VO2)
            fa = fetch_fitness_age(api, dates[-1])
            if FAGE.exists(): touched.append(FAGE)
            if fa.get(dates[-1].isoformat()): log(f"fitness age {fa[dates[-1].isoformat()].get('fitnessAge')}")
            if first < dates[0]:   # apply that history to earlier days too, from saved raw files
                d = first
                while d < dates[0]:
                    rp = RAW / str(d.year) / f"{d.isoformat()}.json"
                    if rp.exists():
                        p_, ch = apply(d, json.loads(rp.read_text()))
                        if ch: touched.append(p_); summary.append(f"{d.strftime('%d %b')} {', '.join(ch)}")
                    d += dt.timedelta(days=1)
        for d in dates:
            rp = RAW / str(d.year) / f"{d.isoformat()}.json"
            if a.remap:
                if not rp.exists(): continue
                raw = json.loads(rp.read_text())
            else:
                raw, rp = fetch_day(api, d); time.sleep(1)   # be gentle with Garmin
                touched.append(rp)
                for act in raw.get("activities") or []:
                    ap_ = fetch_activity_detail(api, act)
                    if ap_: touched.append(ap_)
            p, changes = apply(d, raw)
            if changes:
                touched.append(p); summary.append(f"{d.strftime('%d %b')} {', '.join(changes)}")
                log(d, "->", ", ".join(changes))
            else:
                log(d, "no change")
        pushed = None
        if not a.no_git and touched:
            pushed = commit_and_push(touched, "; ".join(summary) if summary else f"raw {dates[0]}..{dates[-1]}")
        recent = str(today - dt.timedelta(days=1))   # only flag gaps that matter now: today and yesterday
        warnings = [{"date": d, "part": part, "error": err} for d, part, err in WARN if d >= recent]
        now = bkenv.now().isoformat(timespec="seconds")
        save_state(last_success=now, last_error=None, last_range=[str(dates[0]), str(dates[-1])],
                   last_changes=summary[-10:], last_push_ok=pushed, last_warnings=warnings,
                   **({"last_push_error_at": now} if pushed is False else {}))
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        if "login" in msg.lower() or "auth" in msg.lower() or "token" in msg.lower() or "401" in msg:
            msg += " — run: .venv/bin/python scripts/garmin_login.py"
        save_state(last_error=msg, last_error_at=bkenv.now().isoformat(timespec="seconds"))
        log("FAILED:", msg); traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
