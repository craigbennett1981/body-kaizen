#!/usr/bin/env python3
"""Body Kaizen local dashboard. Stdlib only (+ PyYAML).

run:  python3 app/server.py            -> http://127.0.0.1:8765
"""
import datetime as dt, hmac, http.cookies, importlib, json, os, pathlib, re, secrets, sys, time, traceback, urllib.parse
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
import thresholds  # noqa: E402
import datasetup  # noqa: E402
import connections  # noqa: E402
import muscles  # noqa: E402
import pace  # noqa: E402
import energybalance  # noqa: E402
import foods  # noqa: E402
import sleep  # noqa: E402
import experiments  # noqa: E402
import assistant  # noqa: E402
import intensity  # noqa: E402
import maintenance  # noqa: E402

STATIC = pathlib.Path(__file__).resolve().parent / "static"
HOST = os.environ.get("FT_HOST", "127.0.0.1")   # localhost only — never exposed to the network
PORT = int(os.environ.get("FT_PORT", "8765"))
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
# Requests must name this server in their Host header. A web page can't then read the dashboard through a
# rebound DNS name (DNS rebinding): its requests carry the attacker's host name and are refused.
ALLOWED_HOSTS = {f"{h}:{PORT}" for h in ("127.0.0.1", "localhost", "[::1]")} | {f"{HOST}:{PORT}"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS}
# A fresh secret each time the server starts. Only the dashboard's own page gets it (written into index.html as it
# is served); every request that changes anything must send it back in the X-BK-Token header.
SESSION_TOKEN = secrets.token_urlsafe(32)
# Signing in: every request, reads included, needs a cookie holding the secret in ~/.body-kaizen/session.key, which
# only your account can read. `body-kaizen` (or `body-kaizen open`) opens the browser on a link carrying it; the server
# turns that into the cookie and drops the key from the address. Other accounts on this computer, and anything else
# that can reach the port, get the sign-in page and no data. (The same pattern as Jupyter's token.)
SIGNIN_KEY = data.bkenv.session_key()
COOKIE = f"bk_session_{PORT}"   # one per port: a demo on another port has its own
COOKIE_AGE = 365 * 86400
# The logo, served to anyone (it holds no data): browsers ask for it before and after signing in.
# Each address maps to a fixed file name, so nothing from the request goes into the path that's opened.
ICONS = {"/favicon.ico": ("favicon.ico", "image/x-icon"), "/favicon.svg": ("favicon.svg", "image/svg+xml"),
         "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
         "/icon-192.png": ("icon-192.png", "image/png"), "/icon-512.png": ("icon-512.png", "image/png")}
PAGES = ("/",) + tuple("/" + f.name for f in sorted(STATIC.glob("*.html")))   # where the sign-in link may lead
SIGNIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<title>Body Kaizen: open from your account</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111318;color:#EBEEF5;font:16px/1.5 system-ui,sans-serif}
main{max-width:520px;padding:28px} h1{font-size:24px;margin:0 0 12px} p{color:#AEB5C2} code{background:#1E222B;padding:2px 7px;border-radius:6px;color:#EBEEF5}
</style></head><body><main><h1>Body Kaizen is running, but this browser isn't signed in</h1>
<p>Only the account that runs the dashboard can open it. On that account, click <b>Body Kaizen</b> in your
Applications folder or Start menu, or run <code>body-kaizen open</code> (<code>python -m body_kaizen open</code> from
the code folder), and it opens this browser signed in.</p>
<p>It's once per browser: you stay signed in across restarts.</p></main></body></html>"""
MAX_BODY = 10_000
CSP = ("default-src 'self'; script-src 'self'{nonce}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
# Query parameters the API takes, and what each must look like. Anything else is refused before it reaches the code
# (a date is used to build a file path).
PARAM_OK = {"date": r"\d{4}-\d{2}-\d{2}", "start": r"\d{4}-\d{2}-\d{2}", "end": r"\d{4}-\d{2}-\d{2}",
            "days": r"\d{1,4}", "i": r"\d{1,3}", "now": r"\d{2}:\d{2}", "id": r"[A-Za-z0-9_.:-]{1,80}"}


def _days(q, default, most):
    """A `days` parameter, kept between 1 and `most`: a huge one would make the server work through years of data."""
    return max(1, min(most, int(q.get("days", [default])[0])))


def params_ok(q):
    import re
    for k, vals in q.items():
        pat = PARAM_OK.get(k)
        if pat is None or any(not re.fullmatch(pat, v) for v in vals): return False
        if k in ("date", "start", "end"):
            try: [dt.date.fromisoformat(v) for v in vals]
            except ValueError: return False
    return True
SETUP_MODE = data.bkenv.needs_data_setup()   # no data folder yet: serve only the first-run folder setup


def _exp_reminders():
    """Experiment reminders ride along with the alerts as toasts; a broken experiments.yaml must not stop the alerts."""
    try: return experiments.reminders()
    except Exception as e:
        print("experiment reminders failed:", e, flush=True); return []


ROUTES = {
    "/api/summary": lambda q: data.summary(),
    "/api/training": lambda q: data.training(),
    "/api/intensity": lambda q: intensity.build(),
    "/api/maintenance": lambda q: maintenance.build(),
    "/api/body": lambda q: data.body(),
    "/api/reference": lambda q: data.reference(),
    "/api/day": lambda q: data.day_detail(q.get("date", [""])[0]),
    "/api/connections": lambda q: connections.status(),
    "/api/foods": lambda q: foods.build(),
    "/api/sleep": lambda q: sleep.build(),
    "/api/experiments": lambda q: experiments.build(),
    "/api/energy": lambda q: energybalance.build(q.get("date", [None])[0]),
    "/api/garmin": lambda q: {**scheduler.status(), "last_watch_date": insights.last_watch_date(), "watch_upto": glance.watch_upto()},
    "/api/insights": lambda q: insights.for_day(q.get("date", [""])[0]),
    "/api/week": lambda q: weekly.week(q.get("start", [None])[0]),
    "/api/plan": lambda q: planner.plan(),
    "/api/longevity": lambda q: {**longevity.compute(), "lab_alerts": [a for a in alerts.compute() if a["id"].startswith("lab-")]},
    "/api/todo": lambda q: todo.items(),
    "/api/alerts": lambda q: alerts.compute() + _exp_reminders(),
    "/api/timeline": lambda q: timeline.events(),
    "/api/doctor": lambda q: doctor.report(),
    "/api/advice": lambda q: advice.compute(),
    "/api/wellbeing": lambda q: wellbeing.compute(),
    "/api/healthscore": lambda q: healthscore.compute(),
    "/api/workouts": lambda q: workouts.index(),
    "/api/muscles": lambda q: muscles.build(_days(q, 7, 365), q.get("end", [None])[0], q.get("date", [None])[0], q.get("i", [None])[0]),
    "/api/workout": lambda q: workouts.detail(q.get("date", [""])[0], q.get("i", ["0"])[0]),
    "/api/pace": lambda q: pace.build(q.get("date", [data.bkenv.today().isoformat()])[0], q.get("now", [None])[0]),   # now=HH:MM for tests and screenshots
    "/api/profile": lambda q: profile_info(),
    "/api/assistant": lambda q: assistant.build(),   # the set-up prompt for an AI assistant (after first-run setup, and from Profile)
    # The page's write token again, for a tab left open across a server restart. Only a signed-in browser gets it,
    # and only a page on this dashboard's own address can read the reply (Host check, no CORS headers).
    "/api/session": lambda q: {"token": SESSION_TOKEN},
    "/api/glance": lambda q: glance.build(q.get("date", [data.bkenv.today().isoformat()])[0]),
    "/api/daytimeline": lambda q: daytimeline.build(q.get("date", [data.bkenv.today().isoformat()])[0]),
    "/api/glucose_overview": lambda q: glucose.overview(_days(q, 14, 90)),
    "/api/glucose": lambda q: glucose.day(q.get("date", [data.bkenv.today().isoformat()])[0]),
    "/api/thresholds": lambda q: thresholds.build(),
    "/api/readiness": lambda q: {"series": readiness.series(), "backtest": readiness.backtest(), "episodes": readiness.episodes()},
}

# Reload app code when it changes on disk, so edits never leave a stale server running.
MODULES = ["insights", "weekly", "readiness", "planner", "longevity", "habits", "todo", "alerts", "timeline", "doctor", "advice", "wellbeing", "healthscore", "glucose", "daytimeline", "glance", "workouts", "muscles", "pace", "thresholds", "datasetup", "energybalance", "foods", "sleep", "experiments", "intensity", "maintenance"]
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
            "units": B.units(),
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
    units = str(body.get("units") or "metric")
    if units not in data.bkenv.UNITS: return "Units are metric or imperial."
    data.bkenv.save_profile(name, start, tzn, units)
    return None

class Handler(BaseHTTPRequestHandler):
    # A client that connects and then sends nothing (or trickles a request in) is dropped after this many seconds,
    # instead of holding a thread for good. Longer than any real request, which arrives at once from this computer.
    timeout = 30

    def _send(self, code, body, ctype, nonce=None, headers=()):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        for k, v in headers: self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        # Defence in depth against injected markup: only scripts from this server, and on pages only the ones carrying
        # this response's nonce, may run. No inline handlers, no eval, no framing by other sites, no outside requests.
        self.send_header("Content-Security-Policy", CSP.format(nonce=f" 'nonce-{nonce}'" if nonce else ""))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(b)

    def _host_ok(self):
        if (self.headers.get("Host") or "").lower() in ALLOWED_HOSTS: return True
        self._send(421, '{"error":"wrong host"}', "application/json"); return False

    def _signed_in(self):
        try: c = http.cookies.SimpleCookie(self.headers.get("Cookie") or "")
        except http.cookies.CookieError: return False
        return COOKIE in c and hmac.compare_digest(c[COOKIE].value.encode(), SIGNIN_KEY.encode())

    def _signin(self, u):
        """The sign-in link (?key=...): set the cookie and send the browser on to the same address without the key,
        so it isn't left in the address bar, the history or a bookmark. A wrong key just gets the sign-in page."""
        key = urllib.parse.parse_qs(u.query).get("key", [""])[0]
        if not hmac.compare_digest(key.encode(), SIGNIN_KEY.encode()): return self._needs_signin(u)
        # On to one of the dashboard's own pages, never to anything taken from the request: a path like //example.com
        # would send the browser off-site, and request text in a header could split it. Anything else goes to "/".
        to = next((p for p in PAGES if p == u.path), "/")
        cookie = f"{COOKIE}={SIGNIN_KEY}; Path=/; Max-Age={COOKIE_AGE}; HttpOnly; SameSite=Strict"
        self._send(303, "", "text/plain", headers=[("Location", to), ("Set-Cookie", cookie)])

    def _icon(self, path):
        name, ctype = ICONS[path]
        with open(STATIC / name, "rb") as fh: body = fh.read()
        self._send(200, body, ctype, headers=[("Cache-Control", "max-age=86400")])

    def _needs_signin(self, u):
        if u.path.startswith("/api/"): return self._send(401, '{"error":"not signed in","signin":true}', "application/json")
        self._send(401, SIGNIN_PAGE, "text/html; charset=utf-8")

    def do_GET(self):
        if not self._host_ok(): return
        u = urllib.parse.urlparse(self.path)
        if "key" in urllib.parse.parse_qs(u.query): return self._signin(u)
        if u.path in ICONS: return self._icon(u.path)        # the logo only: public, so the sign-in page has it too
        if not self._signed_in(): return self._needs_signin(u)
        try:
            if u.path == "/api/datasetup":
                return self._send(200, json.dumps(datasetup.info()), "application/json")
            if SETUP_MODE:
                if u.path.startswith("/api/"): return self._send(503, '{"error":"choose a data folder first","setup":true}', "application/json")
                if u.path in ("/", "", "/index.html"): u = u._replace(path="/setup.html")
            elif u.path.startswith("/api/"):
                _maybe_reload()
            if u.path in ROUTES:
                q = urllib.parse.parse_qs(u.query)
                if not params_ok(q): return self._send(400, '{"error":"bad parameter"}', "application/json")
                res = ROUTES[u.path](q)
                if res is None: return self._send(404, '{"error":"not found"}', "application/json")
                return self._send(200, json.dumps(res), "application/json")
            name = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
            f = os.path.realpath(os.path.join(STATIC, name))
            if f.startswith(str(STATIC) + os.sep) and os.path.isfile(f):
                ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8",
                         "woff2": "font/woff2", "txt": "text/plain; charset=utf-8",
                         "svg": "image/svg+xml", "png": "image/png", "ico": "image/x-icon"}.get(os.path.splitext(f)[1][1:], "application/octet-stream")
                with open(f, "rb") as fh: body = fh.read()
                nonce = None
                if name.endswith(".html"):
                    body = body.replace(b'name="bk-token" content=""', f'name="bk-token" content="{SESSION_TOKEN}"'.encode(), 1)
                    nonce = secrets.token_urlsafe(16)
                    body = re.sub(rb"<script\b", f'<script nonce="{nonce}"'.encode(), body, flags=re.IGNORECASE)
                return self._send(200, body, ctype, nonce)
            self._send(404, "not found", "text/plain")
        except Exception:
            traceback.print_exc()   # details go to the server log only
            self._send(500, '{"error":"server error: see the server log"}', "application/json")

    def _write_ok(self):
        """Every request that changes something must come from the dashboard's own page. Layers, any one of which
        blocks a hostile website on its own: the Host check (DNS rebinding); the browser-set Origin and
        Sec-Fetch-Site headers (cross-site posts); JSON only (plain HTML forms can't send it); and the per-start
        secret in a custom header, which another site can neither read nor send without a CORS preflight this
        server never answers."""
        h = self.headers
        why = ("signed out" if not self._signed_in() else
               "origin" if h.get("Origin") not in ALLOWED_ORIGINS else
               "site" if h.get("Sec-Fetch-Site") not in (None, "same-origin") else
               "type" if (h.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json" else
               "token" if not hmac.compare_digest(h.get("X-BK-Token") or "", SESSION_TOKEN) else None)
        if why:
            print(f"refused {self.command} {self.path.split('?')[0]}: {why}", file=sys.stderr)
            self._send(403, '{"error":"forbidden"}', "application/json")
            return False
        return True

    def _json_body(self):
        # A negative or malformed length would make read() wait for the client to close the connection
        try: n = int(self.headers.get("Content-Length") or 0)
        except ValueError: n = -1
        if n < 0: self._send(400, '{"error":"bad length"}', "application/json"); return None
        if n > MAX_BODY: self._send(413, '{"error":"too large"}', "application/json"); return None
        try: body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError: self._send(400, '{"error":"bad json"}', "application/json"); return None
        return body if isinstance(body, dict) else {}

    def do_OPTIONS(self):   # never grant a CORS preflight: other sites may not call this server
        self._send(405, '{"error":"not allowed"}', "application/json")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS

    def do_POST(self):
        if not self._host_ok() or not self._write_ok(): return
        try: self._post()
        except Exception:
            traceback.print_exc()   # details go to the server log only, as for GET
            try: self._send(500, '{"error":"server error: see the server log"}', "application/json")
            except OSError: pass   # the client has gone

    def _post(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/datasetup/"):
            if not SETUP_MODE: return self._send(409, '{"error":"a data folder is already set up"}', "application/json")
            body = self._json_body()
            if body is None: return
            act = u.path.rsplit("/", 1)[1]
            if act == "pick": return self._send(200, json.dumps(datasetup.pick()), "application/json")
            if act == "check": return self._send(200, json.dumps(datasetup.check(body.get("path"))), "application/json")
            if act == "create":
                try: res = datasetup.create(body)
                except OSError as e: res = {"ok": False, "error": f"Couldn't create the folder: {e.strerror or e}"}
                return self._send(200 if res.get("ok") else 400, json.dumps(res), "application/json")
            return self._send(404, '{"error":"not found"}', "application/json")
        if SETUP_MODE: return self._send(503, '{"error":"choose a data folder first","setup":true}', "application/json")
        if u.path == "/api/setup":
            body = self._json_body()
            if body is None: return
            err = save_setup(body)
            return self._send(400 if err else 200, json.dumps({"error": err} if err else profile_info()), "application/json")
        if u.path == "/api/todo/toggle":
            item = todo.toggle(urllib.parse.parse_qs(u.query).get("id", [""])[0])
            return self._send(200 if item else 404, json.dumps(item or {"error": "no such item"}), "application/json")
        CONNECT = {"/api/connections/libre/connect": connections.libre_connect,
                   "/api/connections/libre/disconnect": lambda b: connections.libre_disconnect(),
                   "/api/connections/libre/pull": lambda b: connections.libre_pull(),
                   "/api/connections/garmin/connect": connections.garmin_connect,
                   "/api/connections/garmin/disconnect": lambda b: connections.garmin_disconnect(),
                   "/api/connections/garmin/pull": lambda b: connections.garmin_pull()}
        if u.path in CONNECT:
            body = self._json_body()
            if body is None: return
            code, res = CONNECT[u.path](body)
            return self._send(code, json.dumps(res), "application/json")
        if u.path == "/api/garmin/sync":
            st = scheduler.status()
            if st["blocked"]:
                return self._send(409, json.dumps({"error": f"Sync is off: {st['blocked']}", **st}), "application/json")
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
    restarted = bool(os.environ.pop("BK_RESTARTED", None))
    tries = 40 if restarted else 1   # restarted on Windows: wait for the old server to let go
    for i in range(tries):
        try: srv = ThreadingHTTPServer((HOST, PORT), Handler); break
        except OSError:
            if i == tries - 1: raise
            time.sleep(0.25)
    if SETUP_MODE:
        print(f"No data folder yet: open http://{HOST}:{PORT} to choose one.", flush=True)
    elif not os.environ.get("FT_NO_SYNC"): scheduler.start()   # FT_NO_SYNC=1: no Garmin/Libre pulls (tests, demo);
                                                              # start() also refuses demo data and folders inside the repo
    print(f"Body Kaizen dashboard on http://{HOST}:{PORT} (data: {data.ROOT})", flush=True)
    if sys.stdout.isatty() and not os.environ.get("FT_NO_BROWSER") and not restarted:
        # started by hand in a terminal: open the browser signed in, as Jupyter does, and show the link once
        import threading, webbrowser
        url = data.bkenv.signin_url(PORT, "127.0.0.1" if HOST in LOOPBACK else HOST)
        print(f"Opening it in your browser, signed in. If it doesn't open, use this link (it's private to you):\n  {url}", flush=True)
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    else:   # a service: its log may be readable by others, so never the key
        print("To open it signed in: body-kaizen open (or: python -m body_kaizen open, from the code folder)", flush=True)
    srv.serve_forever()

if __name__ == "__main__":
    main()
