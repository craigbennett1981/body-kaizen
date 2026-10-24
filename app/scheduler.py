"""In-process scheduler for the Garmin pull. Runs inside the dashboard server (kept alive by launchd).

Pulls after 08:00, 13:00, 19:00 and 22:00. If the Mac was asleep through a slot, the next check
after waking catches it up. A failed pull retries after 30 minutes. Nothing runs until setup is done.
"""
import datetime as dt, json, pathlib, subprocess, sys, threading, time
from zoneinfo import ZoneInfo

CODE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE / "scripts"))
import bkenv  # noqa: E402
ROOT = bkenv.DATA
STATE = ROOT / "imports" / "garmin" / "state.json"
PULL = CODE / "scripts" / "garmin_pull.py"
TOKENS = pathlib.Path("~/.garminconnect/garmin_tokens.json").expanduser()
SLOTS = (8, 13, 19, 22)
CHECK_EVERY = 300

_lock = threading.Lock()
_running = False
_last_output = ""
_on_done = []

def _state():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def installed():
    r = subprocess.run([sys.executable, "-c", "import garminconnect"], capture_output=True)
    return r.returncode == 0

def status():
    s = _state()
    ready = installed() and TOKENS.exists()
    return {**s, "running": _running, "ready": ready, "installed": installed(), "logged_in": TOKENS.exists(),
            "python": sys.executable, "output_tail": _last_output[-1500:]}

def due(now, s):
    if not (6 <= now.hour <= 23): return False
    last = s.get("last_attempt")
    if not last: return True
    last = dt.datetime.fromisoformat(last)
    if any(last < now.replace(hour=h, minute=0, second=0, microsecond=0) <= now for h in SLOTS): return True
    return bool(s.get("last_error")) and (now - last).total_seconds() > 1800

def run_pull(*args):
    global _running, _last_output
    with _lock:
        if _running: return False
        _running = True
    try:
        r = subprocess.run([sys.executable, str(PULL), *args], cwd=ROOT, capture_output=True, text=True, timeout=1800)
        _last_output = (r.stdout or "") + (r.stderr or "")
        print(_last_output.strip()[-800:], flush=True)
    except Exception as e:
        _last_output = f"{type(e).__name__}: {e}"
    finally:
        _running = False
        for cb in _on_done:
            try: cb()
            except Exception: pass
    return True

def run_pull_async(*args):
    if _running: return False
    threading.Thread(target=run_pull, args=args, daemon=True).start()
    return True

REVIEW_STATE = ROOT / "reviews" / ".last"

def weekly_review_due(now):
    """Sunday from 21:00 (or any later day if Sunday was missed): save the week that started last Monday."""
    week_start = (now.date() - dt.timedelta(days=now.weekday()))
    target = week_start if (now.weekday() == 6 and now.hour >= 21) else week_start - dt.timedelta(days=7)
    try: last = REVIEW_STATE.read_text().strip()
    except Exception: last = ""
    return target.isoformat() if last < target.isoformat() else None

def save_weekly_review(start):
    sys.path.insert(0, str(CODE / "app")); sys.path.insert(0, str(CODE / "scripts"))
    import weekly, garmin_pull
    p = weekly.save(start)
    REVIEW_STATE.write_text(start)
    garmin_pull.commit_and_push([p], p.stem, prefix="weekly review")
    print("weekly review saved:", p.name, flush=True)

LIBRE = CODE / "scripts" / "libre_pull.py"
LIBRE_CFG = bkenv.libre_cfg()
LIBRE_EVERY = 30 * 60
_libre_last = [0.0]
def libre_tick(now):
    """Pull CGM readings every 30 minutes (LibreLinkUp keeps ~12 h, so a missed run loses nothing)."""
    if not LIBRE_CFG.exists() or time.time() - _libre_last[0] < LIBRE_EVERY: return
    _libre_last[0] = time.time()
    def go():
        try:
            r = subprocess.run([sys.executable, str(LIBRE)], cwd=ROOT, capture_output=True, text=True, timeout=300)
            out = (r.stdout + r.stderr).strip()
            if out: print(out, flush=True)
        except Exception as e:
            print("libre:", e, flush=True)
    threading.Thread(target=go, daemon=True).start()

def _loop():
    time.sleep(20)
    while True:
        try:
            now = bkenv.now()
            if TOKENS.exists() and due(now, _state()):
                run_pull()
            libre_tick(now)
            wk = weekly_review_due(now)
            if wk: save_weekly_review(wk)
        except Exception as e:
            print("scheduler:", e, flush=True)
        time.sleep(CHECK_EVERY)

def start():
    threading.Thread(target=_loop, daemon=True, name="garmin-scheduler").start()
