#!/usr/bin/env python3
"""Body Kaizen local dashboard. Stdlib only (+ PyYAML).

run:  python3 app/server.py            -> http://127.0.0.1:8765
"""
import datetime as dt, importlib, json, os, pathlib, sys, traceback, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import data  # noqa: E402
import scheduler  # noqa: E402
import insights  # noqa: E402
import weekly  # noqa: E402
import readiness  # noqa: E402
import planner  # noqa: E402
import longevity  # noqa: E402
import todo  # noqa: E402
import alerts  # noqa: E402
import timeline  # noqa: E402
import doctor  # noqa: E402
import advice  # noqa: E402
import wellbeing  # noqa: E402
import healthscore  # noqa: E402
import glucose  # noqa: E402
import daytimeline  # noqa: E402
import glance  # noqa: E402
import workouts  # noqa: E402
import muscles  # noqa: E402
import pace  # noqa: E402

STATIC = pathlib.Path(__file__).resolve().parent / "static"
HOST = os.environ.get("FT_HOST", "127.0.0.1")   # localhost only — never exposed to the network
PORT = int(os.environ.get("FT_PORT", "8765"))
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
# Requests must name this server in their Host header. A web page can't then read the dashboard through a
# rebound DNS name (DNS rebinding): its requests carry the attacker's host name and are refused.
ALLOWED_HOSTS = {f"{h}:{PORT}" for h in ("127.0.0.1", "localhost", "[::1]")} | {f"{HOST}:{PORT}"}

ROUTES = {
    "/api/summary": lambda q: data.summary(),
    "/api/training": lambda q: data.training(),
    "/api/body": lambda q: data.body(),
    "/api/reference": lambda q: data.reference(),
    "/api/day": lambda q: data.day_detail(q.get("date", [""])[0]),
    "/api/garmin": lambda q: {**scheduler.status(), "last_watch_date": insights.last_watch_date(), "watch_upto": glance.watch_upto()},
    "/api/insights": lambda q: insights.for_day(q.get("date", [""])[0]),
    "/api/week": lambda q: weekly.week(q.get("start", [None])[0]),
    "/api/plan": lambda q: planner.plan(),
    "/api/longevity": lambda q: {**longevity.compute(), "lab_alerts": [a for a in alerts.compute() if a["id"].startswith("lab-")]},
    "/api/todo": lambda q: todo.items(),
    "/api/alerts": lambda q: alerts.compute(),
    "/api/timeline": lambda q: timeline.events(),
    "/api/doctor": lambda q: doctor.report(),
    "/api/advice": lambda q: advice.compute(),
    "/api/wellbeing": lambda q: wellbeing.compute(),
    "/api/healthscore": lambda q: healthscore.compute(),
    "/api/workouts": lambda q: workouts.index(),
    "/api/muscles": lambda q: muscles.build(int(q.get("days", ["7"])[0]), q.get("end", [None])[0], q.get("date", [None])[0], q.get("i", [None])[0]),
    "/api/workout": lambda q: workouts.detail(q.get("date", [""])[0], q.get("i", ["0"])[0]),
    "/api/pace": lambda q: pace.build(q.get("date", [data.bkenv.today().isoformat()])[0], q.get("now", [None])[0]),   # now=HH:MM for tests and screenshots
    "/api/profile": lambda q: profile_info(),
    "/api/glance": lambda q: glance.build(q.get("date", [data.bkenv.today().isoformat()])[0]),
    "/api/daytimeline": lambda q: daytimeline.build(q.get("date", [data.bkenv.today().isoformat()])[0]),
    "/api/glucose_overview": lambda q: glucose.overview(int(q.get("days", ["14"])[0])),
    "/api/glucose": lambda q: glucose.day(q.get("date", [data.bkenv.today().isoformat()])[0]),
    "/api/readiness": lambda q: {"series": readiness.series(), "backtest": readiness.backtest(), "episodes": readiness.episodes()},
}

# Reload app code when it changes on disk, so edits never leave a stale server running.
MODULES = ["insights", "weekly", "readiness", "planner", "longevity", "habits", "todo", "alerts", "timeline", "doctor", "advice", "wellbeing", "healthscore", "glucose", "daytimeline", "glance", "workouts", "muscles", "pace"]
_HERE = pathlib.Path(data.__file__).parent
_CODE = [_HERE / "data.py", _HERE.parent / "scripts" / "nutrition.py"] + [_HERE / f"{n}.py" for n in MODULES]
_code_mtime = tuple(f.stat().st_mtime for f in _CODE if f.exists())   # baseline at startup, not first request: an edit made
# between start-up and the first request would otherwise never be picked up
_SELF = pathlib.Path(__file__).resolve(); _SELF_MTIME = _SELF.stat().st_mtime
def _maybe_restart():
    """server.py itself can't be hot-reloaded: exit and let launchd (KeepAlive) start the new version."""
    if os.environ.get("FT_NO_SELF_RESTART") or _SELF.stat().st_mtime == _SELF_MTIME: return
    import threading
    print("server.py changed; restarting via launchd", flush=True)
    threading.Timer(1.0, os._exit, (0,)).start()

def _maybe_reload():
    _maybe_restart()
    """Reload app modules after edits. Each module reloads on its own, so one broken or removed module
    can't take every endpoint down with it."""
    global _code_mtime, data
    m = tuple(f.stat().st_mtime for f in _CODE if f.exists())
    if _code_mtime is not None and m != _code_mtime:
        for mod in [data.N, data] + [sys.modules[n] for n in MODULES if n in sys.modules]:
            try:
                fresh = importlib.reload(mod)
                if mod is data: data = fresh
            except Exception as e:
                print(f"reload of {getattr(mod, '__name__', mod)} failed: {e}", flush=True)
        for n in MODULES:
            if n in sys.modules and hasattr(sys.modules[n], "data"): sys.modules[n].data = data
        globals().update({n: sys.modules[n] for n in MODULES if n in sys.modules})
        print("reloaded app code", flush=True)
    _code_mtime = m

def profile_info():
    B = data.bkenv; p = B.profile(); s = B.settings()
    return {"name": p.get("name"), "start_date": str(p["start_date"]) if p.get("start_date") else None, "timezone": s.get("timezone"),
            "needs_setup": not (p.get("name") and p.get("start_date") and s.get("timezone")),
            "suggested": {"start_date": B.first_day() or B.today().isoformat(), "timezone": B.local_tz_name()}}

def save_setup(body):
    """First-run setup from the dashboard: name, start date, timezone -> settings.yaml. Returns an error string or None."""
    from zoneinfo import ZoneInfo
    name = str(body.get("name") or "").strip(); start = str(body.get("start_date") or ""); tzn = str(body.get("timezone") or "")
    if not 0 < len(name) <= 60 or any(c in name for c in "\n\r<>{}"): return "Enter a name (up to 60 characters)."
    try: dt.date.fromisoformat(start)
    except ValueError: return "Enter the start date as YYYY-MM-DD."
    try: ZoneInfo(tzn)
    except Exception: return f"Unknown timezone: {tzn!r}"
    data.bkenv.save_profile(name, start, tzn)
    return None

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _host_ok(self):
        if (self.headers.get("Host") or "").lower() in ALLOWED_HOSTS: return True
        self._send(421, '{"error":"wrong host"}', "application/json"); return False

    def do_GET(self):
        if not self._host_ok(): return
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path.startswith("/api/"):
                _maybe_reload()
            if u.path in ROUTES:
                res = ROUTES[u.path](urllib.parse.parse_qs(u.query))
                if res is None: return self._send(404, '{"error":"not found"}', "application/json")
                return self._send(200, json.dumps(res), "application/json")
            name = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
            f = (STATIC / name).resolve()
            if STATIC in f.parents and f.is_file():
                ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8",
                         "woff2": "font/woff2", "txt": "text/plain; charset=utf-8"}.get(f.suffix[1:], "application/octet-stream")
                return self._send(200, f.read_bytes(), ctype)
            self._send(404, "not found", "text/plain")
        except Exception:
            traceback.print_exc()   # details go to the server log only
            self._send(500, '{"error":"server error: see the server log"}', "application/json")

    def do_POST(self):
        if not self._host_ok(): return
        # Only this page may trigger actions: a custom header can't be sent cross-site without a CORS
        # preflight, which this server never answers, and the Origin must be the dashboard itself.
        origin = self.headers.get("Origin")
        allowed = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}
        if self.headers.get("X-Logbook") != "1" or (origin and origin not in allowed):
            return self._send(403, '{"error":"forbidden"}', "application/json")
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/setup":
            n = int(self.headers.get("Content-Length") or 0)
            if n > 10_000: return self._send(413, '{"error":"too large"}', "application/json")
            try: body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError: return self._send(400, '{"error":"bad json"}', "application/json")
            err = save_setup(body if isinstance(body, dict) else {})
            return self._send(400 if err else 200, json.dumps({"error": err} if err else profile_info()), "application/json")
        if u.path == "/api/todo/toggle":
            item = todo.toggle(urllib.parse.parse_qs(u.query).get("id", [""])[0])
            return self._send(200 if item else 404, json.dumps(item or {"error": "no such item"}), "application/json")
        if u.path == "/api/garmin/sync":
            st = scheduler.status()
            if not st["ready"]:
                return self._send(409, json.dumps({"error": "Garmin isn't set up yet", **st}), "application/json")
            started = scheduler.run_pull_async()
            return self._send(202, json.dumps({"started": started}), "application/json")
        self._send(404, '{"error":"not found"}', "application/json")

    def log_message(self, fmt, *args):
        if os.environ.get("FT_LOG"): super().log_message(fmt, *args)

def main():
    if HOST not in LOOPBACK and os.environ.get("FT_ALLOW_REMOTE") != "1":
        sys.exit(f"Refusing to listen on {HOST}: the dashboard has no login, so it only runs on this computer "
                 "(127.0.0.1). Set FT_ALLOW_REMOTE=1 only if you've put your own authentication in front of it.")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    if not os.environ.get("FT_NO_SYNC"): scheduler.start()   # FT_NO_SYNC=1: no Garmin/Libre pulls (tests, demo)
    print(f"Body Kaizen dashboard on http://{HOST}:{PORT} (data: {data.ROOT})", flush=True)
    srv.serve_forever()

if __name__ == "__main__":
    main()
