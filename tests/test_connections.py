"""Connections page: the LibreLinkUp and Garmin logins from the dashboard. Fake LibreLinkUp and Garmin libraries
and a fake keychain stand in for the real ones, so nothing here touches the network or your keychain. Standard library only."""
import enum, http.client, json, os, pathlib, re, socket, subprocess, sys, tempfile, time, types, unittest, urllib.request
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scripts")]
os.environ.setdefault("FT_DATA", str(ROOT / "demo"))
os.environ.setdefault("BK_CONFIG", str(pathlib.Path(tempfile.gettempdir()) / "bk-test-config.json"))
import bkenv, garmin_login, libre_login  # noqa: E402

SECRET = "correct horse battery staple"


def fake_libre(patients=1, auth_error=None, redirect_to=None):
    """sys.modules entries for a fake pylibrelinkup and keyring. Returns (modules, keychain dict)."""
    X = types.ModuleType("pylibrelinkup.exceptions")
    class PyLibreLinkUpError(Exception): pass
    class AuthenticationError(PyLibreLinkUpError): pass
    class RedirectError(PyLibreLinkUpError):
        def __init__(self, region): self.region = region; super().__init__(region)
    class TermsOfUseError(PyLibreLinkUpError): pass
    class PrivacyPolicyError(PyLibreLinkUpError): pass
    class EmailVerificationError(PyLibreLinkUpError): pass
    for c in (PyLibreLinkUpError, AuthenticationError, RedirectError, TermsOfUseError, PrivacyPolicyError, EmailVerificationError):
        setattr(X, c.__name__, c)
    APIUrl = enum.Enum("APIUrl", "AP EU US")
    class Client:
        def __init__(self, email, password, api_url): self.api_url = api_url; self.password = password
        def authenticate(self):
            if redirect_to and self.api_url.name != redirect_to: raise RedirectError(APIUrl[redirect_to])
            if auth_error: raise auth_error(self.password) if auth_error is Exception else auth_error()
            if self.password != SECRET: raise AuthenticationError("Invalid login credentials")
        def get_patients(self):
            return [types.SimpleNamespace(patient_id="11111111-2222-3333-4444-555555555555", first_name="Sam", last_name="Demo")][:patients]
        def _get_graph_data_json(self, pid):
            return {"data": {"graphData": [], "connection": {"glucoseMeasurement": {"ValueInMgPerDl": 99, "FactoryTimestamp": "11/4/2026 6:00:00 AM"}}}}
    lib = types.ModuleType("pylibrelinkup"); lib.PyLibreLinkUp = Client; lib.APIUrl = APIUrl; lib.exceptions = X
    chain = {}
    kr = types.ModuleType("keyring")
    kr.set_password = lambda s, u, p: chain.__setitem__((s, u), p)
    kr.get_password = lambda s, u: chain.get((s, u))
    def delete(s, u): chain.pop((s, u))
    kr.delete_password = delete
    return {"pylibrelinkup": lib, "pylibrelinkup.exceptions": X, "keyring": kr}, chain


class Login(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = pathlib.Path(self.tmp.name)
        self.new, self.old = t / "libre.json", t / "old" / "libre.json"
        self.patches = [mock.patch.object(libre_login, "CFG", self.new), mock.patch.object(bkenv, "LIBRE_CFG_NEW", self.new),
                        mock.patch.object(bkenv, "LIBRE_CFG_OLD", self.old)]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()

    def test_connect_saves_password_to_keychain_and_the_rest_privately(self):
        mods, chain = fake_libre(redirect_to="EU")
        with mock.patch.dict(sys.modules, mods):
            r = libre_login.connect(" me@example.com ", SECRET)
        self.assertEqual((r["email"], r["region"], r["patient"]), ("me@example.com", "EU", "Sam Demo"))
        self.assertAlmostEqual(r["latest"]["mmol"], 5.5, places=1)
        self.assertEqual(chain[(bkenv.LIBRE_SERVICE_NEW, "me@example.com")], SECRET)
        saved = self.new.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, saved); self.assertEqual(json.loads(saved)["region"], "EU")
        if os.name == "posix": self.assertEqual(self.new.stat().st_mode & 0o777, 0o600)
        st = libre_login.status()
        self.assertTrue(st["connected"]); self.assertNotIn(SECRET, json.dumps(st))

    def test_failures_are_plain_messages_without_the_password(self):
        cases = [(dict(), "wrong password", "didn't accept"), (dict(patients=0), SECRET, "no one is sharing"),
                 (dict(auth_error=Exception), SECRET, "Couldn't reach LibreLinkUp"), (dict(), "", "Enter your")]
        for kw, pw, expect in cases:
            mods, chain = fake_libre(**kw)
            with self.subTest(expect=expect), mock.patch.dict(sys.modules, mods):
                with self.assertRaises(libre_login.LoginError) as e: libre_login.connect("me@example.com", pw)
                self.assertIn(expect, str(e.exception))
                if pw: self.assertNotIn(pw, str(e.exception))
                self.assertEqual(chain, {}); self.assertFalse(self.new.exists())

    def test_disconnect_forgets_both_locations(self):
        mods, chain = fake_libre()
        with mock.patch.dict(sys.modules, mods):
            libre_login.connect("me@example.com", SECRET)
            self.old.parent.mkdir(); self.old.write_text('{"email": "old@example.com"}')
            chain[(bkenv.LIBRE_SERVICE_OLD, "old@example.com")] = "x"
            st = libre_login.disconnect()
        self.assertFalse(st["connected"]); self.assertEqual(chain, {})
        self.assertFalse(self.new.exists() or self.old.exists())


def fake_garmin(mfa=False, code="123456"):
    m = types.ModuleType("garminconnect")
    class Auth(Exception): pass
    class Conn(Exception): pass
    class Busy(Exception): pass
    class Client:
        def dump(self, path): p = pathlib.Path(path); p.mkdir(parents=True, exist_ok=True); (p / "garmin_tokens.json").write_text('{"di_token": "t"}')
    class Garmin:
        def __init__(self, email=None, password=None, return_on_mfa=False):
            self.password, self.client, self.full_name = password, Client(), None
        def login(self, tokenstore=None):
            if self.password != SECRET: raise Auth(f"bad login for {self.password}")
            return ("needs_mfa", {"cookies": "x"}) if mfa else (None, None)
        def resume_login(self, state, c):
            if c != code: raise Auth("Widget MFA failed: wrong code")
            return None, None
        def _load_profile_and_settings(self): self.full_name = "Sam Demo"
        def get_full_name(self): return self.full_name
    m.Garmin, m.GarminConnectAuthenticationError, m.GarminConnectConnectionError, m.GarminConnectTooManyRequestsError = Garmin, Auth, Conn, Busy
    return {"garminconnect": m}


class GarminLogin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = pathlib.Path(self.tmp.name) / ".garminconnect"
        self.file = t / "garmin_tokens.json"
        self.patches = [mock.patch.object(garmin_login, "TOKENS", str(t)), mock.patch.object(garmin_login, "TOKEN_FILE", self.file)]
        for p in self.patches: p.start()
        garmin_login.cancel()

    def tearDown(self):
        for p in self.patches: p.stop()
        garmin_login.cancel(); self.tmp.cleanup()

    def test_login_without_two_step_saves_the_token(self):
        with mock.patch.dict(sys.modules, fake_garmin()):
            r = garmin_login.start("me@example.com", SECRET)
        self.assertEqual(r, {"connected": True, "name": "Sam Demo"})
        self.assertTrue(self.file.exists()); self.assertNotIn(SECRET, self.file.read_text(encoding="utf-8"))

    def test_two_step_login_with_a_wrong_code_then_the_right_one(self):
        with mock.patch.dict(sys.modules, fake_garmin(mfa=True)):
            r = garmin_login.start("me@example.com", SECRET)
            self.assertTrue(r["needs_mfa"]); self.assertFalse(self.file.exists())
            with self.assertRaises(garmin_login.LoginError) as e: garmin_login.finish(r["login_id"], "000000")
            self.assertIn("didn't work", str(e.exception))
            with self.assertRaises(garmin_login.LoginError) as e: garmin_login.finish(r["login_id"], "abc")
            self.assertIn("digits", str(e.exception))
            self.assertTrue(garmin_login.finish(r["login_id"], "123 456")["connected"])
            self.assertTrue(self.file.exists())
            with self.assertRaises(garmin_login.LoginError) as e: garmin_login.finish(r["login_id"], "123456")
            self.assertIn("expired", str(e.exception))   # used up

    def test_two_step_login_expires_and_limits_tries(self):
        with mock.patch.dict(sys.modules, fake_garmin(mfa=True)):
            r = garmin_login.start("me@example.com", SECRET)
            for _ in range(garmin_login.MAX_TRIES):
                with self.assertRaises(garmin_login.LoginError): garmin_login.finish(r["login_id"], "000000")
            with self.assertRaises(garmin_login.LoginError) as e: garmin_login.finish(r["login_id"], "123456")
            self.assertIn("Too many", str(e.exception))
            r = garmin_login.start("me@example.com", SECRET)
            with mock.patch.object(garmin_login.time, "monotonic", return_value=time.monotonic() + garmin_login.PENDING_TTL + 1):
                with self.assertRaises(garmin_login.LoginError) as e: garmin_login.finish(r["login_id"], "123456")
            self.assertIn("expired", str(e.exception)); self.assertFalse(self.file.exists())

    def test_bad_password_message_never_contains_it(self):
        with mock.patch.dict(sys.modules, fake_garmin()):
            with self.assertRaises(garmin_login.LoginError) as e: garmin_login.start("me@example.com", "hunter2-wrong")
        self.assertIn("didn't accept", str(e.exception)); self.assertNotIn("hunter2", str(e.exception))

    def test_disconnect_deletes_the_token(self):
        with mock.patch.dict(sys.modules, fake_garmin()): garmin_login.start("me@example.com", SECRET)
        garmin_login.disconnect(); self.assertFalse(self.file.exists())


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


class Endpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.port = free_port(); cls.base = f"http://127.0.0.1:{cls.port}"
        env = {**os.environ, "FT_DATA": str(ROOT / "demo"), "BK_CONFIG": str(pathlib.Path(cls.tmp.name) / "config.json"),
               "FT_NO_SYNC": "1", "FT_NO_SELF_RESTART": "1", "FT_PORT": str(cls.port), "HOME": cls.tmp.name}
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / "app" / "server.py")], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        for _ in range(75):
            try:
                with urllib.request.urlopen(cls.base + "/connections.html", timeout=3) as r: cls.page = r.read().decode(); break
            except OSError: time.sleep(0.2)
        cls.token = re.search(r'name="bk-token" content="([^"]+)"', cls.page).group(1)

    @classmethod
    def tearDownClass(cls):
        if cls.srv.poll() is None: cls.srv.terminate(); cls.srv.wait(timeout=10)
        cls.srv.stderr.close(); cls.tmp.cleanup()

    def post(self, path, body, token=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", path, body=json.dumps(body).encode(), headers={
            "Host": f"127.0.0.1:{self.port}", "Origin": self.base, "Sec-Fetch-Site": "same-origin",
            "Content-Type": "application/json", "X-BK-Token": token or self.token})
        r = c.getresponse(); out = (r.status, json.loads(r.read() or b"{}")); c.close(); return out

    def test_status_has_no_secrets(self):
        with urllib.request.urlopen(self.base + "/api/connections", timeout=5) as r: st = json.loads(r.read())
        self.assertFalse(st["libre"]["connected"]); self.assertNotIn("password", json.dumps(st))

    def test_connect_needs_the_token_and_never_echoes_the_password(self):
        self.assertEqual(self.post("/api/connections/libre/connect", {"email": "a@b.c", "password": SECRET}, token="nope")[0], 403)
        code, res = self.post("/api/connections/libre/connect", {"email": "a@b.c", "password": SECRET})
        self.assertEqual(code, 400)   # the real library isn't installed here, or the fake login fails: either way a message
        self.assertTrue(res["error"]); self.assertNotIn(SECRET, json.dumps(res))

    def test_garmin_endpoints(self):
        self.assertEqual(self.post("/api/connections/garmin/connect", {"email": "a@b.c", "password": SECRET}, token="nope")[0], 403)
        code, res = self.post("/api/connections/garmin/connect", {"email": "a@b.c", "password": SECRET})
        self.assertEqual(code, 400); self.assertNotIn(SECRET, json.dumps(res))
        code, res = self.post("/api/connections/garmin/connect", {"login_id": "made-up", "code": "123456"})
        self.assertEqual(code, 400); self.assertIn("expired", res["error"])
        self.assertEqual(self.post("/api/connections/garmin/pull", {})[0], 409)
        with urllib.request.urlopen(self.base + "/api/connections", timeout=5) as r: self.assertFalse(json.loads(r.read())["garmin"]["connected"])

    def test_pull_and_disconnect_when_not_connected(self):
        self.assertEqual(self.post("/api/connections/libre/pull", {})[0], 409)
        code, res = self.post("/api/connections/libre/disconnect", {})
        self.assertEqual(code, 200); self.assertFalse(res["libre"]["connected"])

    def test_zz_password_never_reaches_the_server_log(self):
        self.post("/api/connections/libre/connect", {"email": "a@b.c", "password": SECRET})
        self.post("/api/connections/garmin/connect", {"email": "a@b.c", "password": SECRET})
        self.srv.terminate(); self.srv.wait(timeout=10)   # runs last: stop the server to read all it logged
        self.assertNotIn(SECRET, self.srv.stderr.read())


if __name__ == "__main__":
    unittest.main()
