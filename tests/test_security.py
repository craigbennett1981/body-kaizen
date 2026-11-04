"""The dashboard refuses any request that changes something unless it comes from the dashboard's own page.
Starts the server on a temporary copy of the demo folder and tries each way a hostile website (or another
program) could get in. Standard library only."""
import http.client, json, os, pathlib, re, shutil, socket, subprocess, sys, tempfile, time, unittest, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


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
        env = {**os.environ, "FT_DATA": str(data), "FT_NO_SYNC": "1", "FT_NO_SELF_RESTART": "1", "FT_PORT": str(cls.port)}
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / "app" / "server.py")], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
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
        h = {"Host": host or f"127.0.0.1:{self.port}", **headers}
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


if __name__ == "__main__":
    unittest.main()
