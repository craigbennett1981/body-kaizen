"""The dashboard refuses any request that changes something unless it comes from the dashboard's own page.
Starts the server on a temporary copy of the demo folder and tries each way a hostile website (or another
program) could get in. Standard library only."""
import http.client, json, os, pathlib, re, shutil, socket, subprocess, sys, tempfile, time, unittest, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); import signin   # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


class WriteProtection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        data = pathlib.Path(cls.tmp.name) / "data"
        shutil.copytree(ROOT / "demo", data)
        cls.port = free_port()
        cls.config = signin.env(cls.tmp.name)
        env = {**os.environ, "FT_DATA": str(data), "FT_NO_SYNC": "1", "FT_NO_SELF_RESTART": "1", "FT_PORT": str(cls.port), "BK_CONFIG": cls.config}
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / "app" / "server.py")], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.cookie = signin.sign_in(cls.port, cls.config)
        for _ in range(50):
            try: page = urllib.request.urlopen(cls.base + "/", timeout=1).read().decode(); break
            except OSError: time.sleep(0.2)
        cls.token = re.search(r'name="bk-token" content="([^"]+)"', page).group(1)
        cls.origin = cls.base

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate(); cls.srv.wait(timeout=10); cls.tmp.cleanup()

    def req(self, method="POST", path="/api/todo/toggle?id=nope", host=None, **headers):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}", "Cookie": self.cookie, **headers}
        h = {k: v for k, v in h.items() if v is not None}
        body = h.pop("body", "{}")
        c.request(method, path, body=body.encode() if body is not None else None, headers=h)
        r = c.getresponse(); out = (r.status, r.read(), dict(r.getheaders())); c.close(); return out

    def good(self, **over):
        h = {"Origin": self.origin, "Sec-Fetch-Site": "same-origin", "Content-Type": "application/json", "X-BK-Token": self.token}
        h.update(over); return {k: v for k, v in h.items() if v is not None}

    def test_token_is_written_into_the_page(self):
        self.assertGreaterEqual(len(self.token), 32)

    def test_dashboard_request_is_allowed(self):
        status, body, _ = self.req(**self.good())
        self.assertEqual(status, 404)          # past the guard: the to-do item just doesn't exist
        self.assertIn(b"no such item", body)

    def test_refused(self):
        cases = {
            "another website": self.good(Origin="https://evil.example"),
            "no Origin": self.good(Origin=None),
            "cross-site fetch": self.good(**{"Sec-Fetch-Site": "cross-site"}),
            "form-style post": self.good(**{"Content-Type": "application/x-www-form-urlencoded"}),
            "plain-text post": self.good(**{"Content-Type": "text/plain"}),
            "missing token": self.good(**{"X-BK-Token": None}),
            "wrong token": self.good(**{"X-BK-Token": "x" * 43}),
        }
        for name, h in cases.items():
            with self.subTest(name):
                self.assertEqual(self.req(**h)[0], 403)

    def test_dns_rebinding_host_refused(self):
        self.assertEqual(self.req(host=f"evil.example:{self.port}", **self.good())[0], 421)

    def test_no_cors_preflight(self):
        status, _, headers = self.req("OPTIONS", Origin="https://evil.example", body=None,
                                      **{"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-bk-token"})
        self.assertNotEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_reads_grant_no_cross_site_access(self):
        _, _, headers = self.req("GET", "/api/summary", Origin="https://evil.example", body=None)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_session_token_matches_page(self):
        with urllib.request.urlopen(self.base + "/api/session", timeout=5) as r:
            self.assertEqual(json.loads(r.read())["token"], self.token)

    def test_oversized_body_refused(self):
        status, _, _ = self.req(path="/api/setup", body=json.dumps({"name": "x" * 20000}), **self.good())
        self.assertEqual(status, 413)


class SignIn(WriteProtection):
    """Only a browser holding the key from ~/.body-kaizen/session.key gets anything: other accounts on this computer,
    and anything else that reaches the port, get the sign-in page and no data."""

    def test_signed_out_gets_no_data(self):
        for path in ("/", "/connections.html", "/app.js", "/api/summary", "/api/session", "/api/day?date=2026-10-23"):
            with self.subTest(path=path):
                status, body, _ = self.req("GET", path, body=None, Cookie=None)
                self.assertEqual(status, 401)
                self.assertNotIn(self.token.encode(), body)
                if not path.startswith("/api/"): self.assertIn(b"isn't signed in", body)
        self.assertEqual(self.req("GET", "/api/summary", body=None, Cookie=f"bk_session_{self.port}=" + "x" * 43)[0], 401)
        self.assertEqual(self.req("GET", "/api/summary", body=None, Cookie="bk_session_1=" + signin._cookies[f"bk_session_{self.port}"])[0], 401)
        self.assertEqual(self.req(**self.good(), Cookie=None)[0], 403)   # writes too, even with the page's token

    def test_sign_in_link_sets_the_cookie_and_drops_the_key(self):
        key = signin._cookies[f"bk_session_{self.port}"]
        status, _, h = self.req("GET", f"/?key={key}", body=None, Cookie=None)
        self.assertEqual(status, 303); self.assertEqual(h["Location"], "/")
        c = h["Set-Cookie"]
        for part in (f"bk_session_{self.port}={key}", "HttpOnly", "SameSite=Strict", "Path=/"): self.assertIn(part, c)
        self.assertEqual(self.req("GET", f"/thresholds.html?key={key}&x=1", body=None, Cookie=None)[2]["Location"], "/thresholds.html?x=1")
        status, _, h = self.req("GET", "/?key=wrong", body=None, Cookie=None)
        self.assertEqual(status, 401); self.assertNotIn("Set-Cookie", h)

    def test_key_file_is_private(self):
        f = signin.key_file(self.config)
        self.assertGreaterEqual(len(f.read_text().strip()), 40)
        if os.name == "posix":
            self.assertEqual(f.stat().st_mode & 0o777, 0o600); self.assertEqual(f.parent.stat().st_mode & 0o777, 0o700)


class Limits(WriteProtection):
    """A request can't make the server hang or grind: bad lengths are refused at once, huge ranges are capped."""

    def raw(self, head):
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as c:
            c.sendall(head.encode()); return c.recv(200).split(b" ")[1]

    def test_negative_or_bad_length_is_refused_not_waited_for(self):
        for n in ("-1", "abc", "1e9"):
            with self.subTest(length=n):
                t = time.time()
                code = self.raw(f"POST /api/setup HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nCookie: {self.cookie}\r\nOrigin: {self.origin}\r\n"
                                f"Sec-Fetch-Site: same-origin\r\nContent-Type: application/json\r\nX-BK-Token: {self.token}\r\nContent-Length: {n}\r\n\r\n")
                self.assertEqual(code, b"400"); self.assertLess(time.time() - t, 3)

    def test_huge_day_ranges_are_capped(self):
        t = time.time()
        self.assertEqual(self.req("GET", "/api/muscles?days=9999", body=None)[0], 200)
        self.assertEqual(self.req("GET", "/api/glucose_overview?days=9999", body=None)[0], 200)
        self.assertLess(time.time() - t, 20)


class Hardening(WriteProtection):
    """Against injected markup and file reads: a strict Content-Security-Policy, no framing, dates checked."""

    def test_every_response_has_the_security_headers(self):
        for path in ("/", "/connections.html", "/api/summary", "/app.js", "/nope"):
            with self.subTest(path=path):
                _, _, h = self.req("GET", path, body=None)
                csp = h.get("Content-Security-Policy", "")
                self.assertIn("script-src 'self'", csp); self.assertIn("frame-ancestors 'none'", csp)
                self.assertNotIn("unsafe-inline' ;", csp.split("script-src")[1].split(";")[0] + " ;")
                self.assertEqual(h.get("X-Frame-Options"), "DENY"); self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")

    def test_page_scripts_carry_this_responses_nonce(self):
        for path in ("/", "/connections.html", "/thresholds.html", "/doctor.html"):
            with self.subTest(path=path):
                _, body, h = self.req("GET", path, body=None)
                nonce = re.search(r"'nonce-([^']+)'", h["Content-Security-Policy"]).group(1)
                tags = re.findall(rb"<script\b[^>]*>", body, re.IGNORECASE)
                self.assertTrue(tags)
                for t in tags: self.assertIn(f'nonce="{nonce}"'.encode(), t)
        n1 = re.search(r"'nonce-([^']+)'", self.req("GET", "/", body=None)[2]["Content-Security-Policy"]).group(1)
        n2 = re.search(r"'nonce-([^']+)'", self.req("GET", "/", body=None)[2]["Content-Security-Policy"]).group(1)
        self.assertNotEqual(n1, n2)

    def test_no_inline_handlers_or_javascript_urls_in_the_front_end(self):
        """Inline handlers wouldn't run under the policy anyway; keep them out so nothing breaks silently."""
        for f in (ROOT / "app" / "static").glob("*.*"):
            if f.suffix not in (".html", ".js"): continue
            txt = f.read_text(encoding="utf-8")
            with self.subTest(file=f.name):
                self.assertIsNone(re.search(r"""<[^>]*\son[a-z]+\s*=\s*["']""", txt), "inline event handler")
                self.assertNotIn("javascript:", txt)

    def test_dates_must_be_dates(self):
        for bad in ("/etc/passwd", "../../../etc/passwd", "2026-10-23/../../x", "2026-13-01", "abc", "2026-10-23%00"):
            with self.subTest(date=bad):
                status, _, _ = self.req("GET", f"/api/day?date={urllib.parse.quote(bad)}", body=None)
                self.assertEqual(status, 400)
        self.assertEqual(self.req("GET", "/api/week?start=..%2F..%2Fx", body=None)[0], 400)
        self.assertEqual(self.req("GET", "/api/muscles?days=abc", body=None)[0], 400)
        self.assertEqual(self.req("GET", "/api/day?date=2026-10-23", body=None)[0], 200)
        self.assertEqual(self.req("GET", "/api/summary?unexpected=1", body=None)[0], 400)

    def test_day_file_refuses_anything_but_a_date(self):
        sys.path[:0] = [str(ROOT / "app"), str(ROOT / "scripts")]
        import data
        for bad in ("/etc/passwd", "../x", "2026-10-23/../../x", ""):
            with self.subTest(date=bad), self.assertRaises(ValueError): data.day_file(bad)
        self.assertEqual(data.day_file("2026-10-23").name, "2026-10-23.yaml")


if __name__ == "__main__":
    unittest.main()
