#!/usr/bin/env python3
"""Pull FreeStyle Libre readings via LibreLinkUp (~12 h of 15-minute history plus the latest reading)
into imports/libre/YYYY-MM-DD.json. Safe to run often; commits at most every 3 hours.
usage: libre_pull.py [--no-git] [--commit]"""
import datetime as dt, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bkenv  # noqa: E402
ROOT = bkenv.DATA
RAW = ROOT / "imports" / "libre"
STATE = RAW / "state.json"
CFG = bkenv.libre_cfg()
SERVICE = bkenv.libre_service()
MGDL = 18.016

def log(*a): print(bkenv.now().strftime("%H:%M:%S"), "libre:", *a, flush=True)
def state():
    try: return json.loads(STATE.read_text())
    except Exception: return {}
def save_state(**kw):
    s = state(); s.update(kw); RAW.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(s, indent=2, default=str))

def to_local(ts):
    if ts.tzinfo is None: ts = ts.replace(tzinfo=dt.timezone.utc)   # FactoryTimestamp is UTC
    return ts.astimezone(bkenv.tz())

def fetch():
    import keyring
    from pylibrelinkup import PyLibreLinkUp, APIUrl
    from pylibrelinkup.exceptions import RedirectError
    cfg = json.loads(CFG.read_text())
    pw = keyring.get_password(SERVICE, cfg["email"])
    if not pw: raise RuntimeError("No LibreLinkUp password in the Keychain; run scripts/libre_login.py")
    region = APIUrl.from_string(cfg.get("region", "AP"))
    try:
        c = PyLibreLinkUp(email=cfg["email"], password=pw, api_url=region); c.authenticate()
    except RedirectError as e:
        c = PyLibreLinkUp(email=cfg["email"], password=pw, api_url=e.region); c.authenticate()
        cfg["region"] = e.region.name; CFG.write_text(json.dumps(cfg, indent=2))
    from uuid import UUID
    raw = c._get_graph_data_json(UUID(cfg["patient_id"]))   # parsed by hand: the library rejects an empty (warming-up) sensor
    return parse_graph(raw)

def _ts(s):
    """LibreLinkUp FactoryTimestamp is UTC, e.g. '10/16/2026 7:21:00 AM'."""
    for f in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try: return dt.datetime.strptime(s, f).replace(tzinfo=dt.timezone.utc)
        except ValueError: pass
    raise ValueError(f"unknown timestamp {s!r}")

def parse_graph(raw):
    d = (raw or {}).get("data") or {}
    items = list(d.get("graphData") or [])
    cur = (d.get("connection") or {}).get("glucoseMeasurement")
    if cur: items.append(cur)
    out = []
    for m in items:
        mg = m.get("ValueInMgPerDl"); ts = m.get("FactoryTimestamp")
        if mg and ts: out.append((to_local(_ts(ts)), round(mg / MGDL, 2)))
    return sorted(set(out))

def merge(readings):
    by_day, touched = {}, []
    for t, v in readings: by_day.setdefault(t.date().isoformat(), {})[t.strftime("%H:%M")] = v
    for day, vals in by_day.items():
        p = RAW / day[:4] / f"{day}.json"; p.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(p.read_text()) if p.exists() else {"date": day, "unit": "mmol/L", "readings": {}}
        n0 = len(old["readings"]); old["readings"].update(vals)
        old["readings"] = dict(sorted(old["readings"].items()))
        if len(old["readings"]) != n0 or not p.exists():
            p.write_text(json.dumps(old, indent=1)); touched.append(p)
    return touched

def main():
    args = sys.argv[1:]
    if not CFG.exists(): log("not set up (run scripts/libre_login.py)"); return 0
    now = bkenv.now()
    try:
        r = fetch(); touched = merge(r)
        last = max((t for t, _ in r), default=None)
        save_state(last_attempt=now.isoformat(timespec="seconds"), last_success=now.isoformat(timespec="seconds"),
                   last_error=None, last_reading=last.isoformat(timespec="minutes") if last else None,
                   latest_mmol=r[-1][1] if r else None)
        log(f"{len(r)} readings, {len(touched)} day file(s) updated")
    except Exception as e:
        save_state(last_attempt=now.isoformat(timespec="seconds"), last_error=f"{type(e).__name__}: {e}"[:400], last_error_at=now.isoformat(timespec="seconds"))
        log("failed:", e); return 1
    s = state(); lc = s.get("last_commit")
    if "--no-git" not in args and ("--commit" in args or not lc or (now - dt.datetime.fromisoformat(lc)).total_seconds() > 3 * 3600):
        import garmin_pull
        files = sorted(RAW.glob("*/*.json"))
        changed = garmin_pull.git("status", "--porcelain", "--", "imports/libre", check=False).stdout.strip()
        if changed:
            garmin_pull.commit_and_push(files, f"glucose to {now:%d %b %H:%M}", prefix="libre")
        save_state(last_commit=now.isoformat(timespec="seconds"))
    return 0

if __name__ == "__main__":
    sys.exit(main())
